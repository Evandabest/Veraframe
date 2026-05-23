import { randomUUID } from 'crypto'
import { unlink } from 'fs/promises'
import { tmpdir } from 'os'
import { resolve as resolvePath } from 'path'
import type { DaemonHandle } from './daemon'
import type { AssetRegistry } from './assets'
import { ffmpegAppend, ffmpegMuxAudio, ffmpegSplice } from './ffmpeg'
import { runTts } from './planner'

export interface RenderProgress {
  step: string
  detail?: string
}

/**
 * Optional incremental-render config. When present, we render ONLY the
 * frames inside `changedWindow` in Blender, then either splice them into
 * `previousVideoPath` (replacing that time range) or append them onto the
 * end. Saves the per-frame rendering time for the unchanged regions.
 *
 * Blender setup (load_scene, load_character, execute_timeline) still runs
 * with the full timeline so the scene state is correct before we render
 * the slice.
 */
export interface IncrementalRender {
  previousVideoPath: string
  changedWindow: { start: number; end: number }
  operation: 'splice' | 'append'
}

export type RenderQuality = 'draft' | 'hifi'

export interface RenderOptions {
  fps?: number
  onProgress?: (event: RenderProgress) => void
  incremental?: IncrementalRender
  /** Render quality preset. 'draft' = small + low-sample (fast iteration);
   *  'hifi' = full resolution + samples (default). For incremental renders,
   *  the splice/append seam quality is best when this matches the base. */
  quality?: RenderQuality
  /** Repo root needed to spawn the TTS subprocess. Required if any talk
   *  action is in the timeline and the user wants audio. */
  repoRoot?: string
  /** Whether to call TTS for `talk` actions. Defaults to false (silent video,
   *  current behavior). When true and `repoRoot` is set, each talk action's
   *  text is synthesized to a WAV and muxed into the final MP4. */
  generateAudio?: boolean
}

export interface RenderResult {
  renderId: string
  videoPath: string
  durationSec: number
  executed: number
  skipped: number
  timeline: Record<string, unknown>
}

/**
 * Run a fully-resolved timeline through the daemon and produce an MP4.
 *
 * Mirrors the orchestration in `planner/cli.py:_cmd_render` but stays in
 * TypeScript: `load_scene` → per-character `load_character` → `execute_timeline`
 * → `render`. Returns `{ renderId, videoPath, ... }` so callers can serve the
 * file under a custom Electron protocol.
 */
export async function runTimeline(
  daemon: DaemonHandle,
  assets: AssetRegistry,
  timeline: Record<string, unknown>,
  options: RenderOptions = {}
): Promise<RenderResult> {
  const fps = options.fps ?? 24
  const quality: RenderQuality = options.quality ?? 'hifi'
  const emit = options.onProgress ?? ((): void => {})

  const sceneId = String(timeline.scene)
  const scene = assets.scenes[sceneId]
  if (!scene) throw new Error(`scene '${sceneId}' not in registry`)

  const shots = (timeline.shots ?? []) as Array<Record<string, unknown>>
  if (shots.length === 0) throw new Error('timeline has no shots')
  const durationSec = Math.max(...shots.map((s) => Number(s.end ?? 0)))
  if (durationSec <= 0) throw new Error('timeline has zero duration')

  const renderId = randomUUID()
  const outputPath = resolvePath(tmpdir(), `veraframe-render-${renderId}.mp4`)

  const assetPaths: Record<string, string> = {}
  for (const [id, anim] of Object.entries(assets.animations)) {
    assetPaths[id] = anim.fbxPath
  }

  emit({ step: 'reset' })
  await daemon.call('reset')

  emit({ step: 'load_scene', detail: sceneId })
  await daemon.call('load_scene', { blend_path: scene.blendPath })

  // Build per-character animation overrides. When a character has its own
  // idle.fbx / walk.fbx (user-uploaded), the executor uses those instead of
  // the global ones. Keyed by the timeline's character handle (id), not the
  // preset id, because actions reference characters by handle.
  const characterAssets: Record<string, Record<string, string>> = {}

  const characters = (timeline.characters ?? []) as Array<Record<string, unknown>>
  for (let i = 0; i < characters.length; i += 1) {
    const character = characters[i]
    const preset = assets.characters[String(character.preset)]
    if (!preset) throw new Error(`character preset '${character.preset}' not in registry`)
    emit({
      step: 'load_character',
      detail: `${character.id} (${i + 1}/${characters.length})`
    })
    await daemon.call('load_character', {
      fbx_path: preset.meshPath,
      spawn_point: String(character.spawn),
      handle: String(character.id)
    })
    if (preset.animations && Object.keys(preset.animations).length > 0) {
      characterAssets[String(character.id)] = preset.animations
    }
  }

  emit({ step: 'execute_timeline' })
  const execResult = (await daemon.call('execute_timeline', {
    timeline,
    asset_paths: assetPaths,
    character_assets: characterAssets,
    fps
  })) as { executed: unknown[]; skipped: unknown[] }

  if (options.incremental) {
    const { previousVideoPath, changedWindow, operation } = options.incremental
    const startFrame = Math.round(changedWindow.start * fps)
    const endFrame = Math.round(changedWindow.end * fps)
    const slicePath = resolvePath(tmpdir(), `veraframe-slice-${randomUUID()}.mp4`)

    emit({
      step: 'render',
      detail: `slice frames ${startFrame}-${endFrame} (${(changedWindow.end - changedWindow.start).toFixed(1)}s)`
    })
    await daemon.call('render', {
      start_frame: startFrame,
      end_frame: endFrame,
      output_path: slicePath,
      fps,
      quality
    })

    emit({ step: 'merge', detail: operation })
    if (operation === 'splice') {
      await ffmpegSplice(
        previousVideoPath,
        slicePath,
        changedWindow.start,
        changedWindow.end,
        outputPath
      )
    } else {
      await ffmpegAppend(previousVideoPath, slicePath, outputPath)
    }

    // The slice file is no longer needed once it has been merged.
    await unlink(slicePath).catch(() => {})
  } else {
    const endFrame = Math.round(durationSec * fps)
    emit({ step: 'render', detail: `${endFrame + 1} frame(s) (${quality})` })
    // Render to a temporary "silent" path; we mux audio in a separate pass
    // afterwards (if there's any audio to mux). Skip the temp file when
    // generateAudio is off — render directly to outputPath.
    const silentPath = options.generateAudio
      ? resolvePath(tmpdir(), `veraframe-silent-${renderId}.mp4`)
      : outputPath
    await daemon.call('render', {
      start_frame: 0,
      end_frame: endFrame,
      output_path: silentPath,
      fps,
      quality
    })

    if (options.generateAudio) {
      const clips = await _synthesizeTalkAudio(
        timeline,
        options.repoRoot,
        emit
      )
      emit({ step: 'mux_audio', detail: `${clips.length} clip(s)` })
      await ffmpegMuxAudio(silentPath, outputPath, clips)
      await unlink(silentPath).catch(() => {})
      // Audio temp files are intentionally NOT cleaned up here — they're
      // small and useful for debugging mis-timed lip-sync. The OS will
      // clean tmpdir eventually.
    }
  }

  return {
    renderId,
    videoPath: outputPath,
    durationSec,
    executed: execResult.executed.length,
    skipped: execResult.skipped.length,
    timeline
  }
}

/** Walk the timeline, run TTS for every `talk` action, and return placement
 *  clips for ffmpegMuxAudio. Failures synthesize-side are logged but do not
 *  abort the render — the action just falls back to silent. */
async function _synthesizeTalkAudio(
  timeline: Record<string, unknown>,
  repoRoot: string | undefined,
  emit: (event: RenderProgress) => void
): Promise<Array<{ audioPath: string; offsetSec: number }>> {
  if (!repoRoot) return []
  const shots = (timeline.shots ?? []) as Array<Record<string, unknown>>
  const clips: Array<{ audioPath: string; offsetSec: number }> = []
  let index = 0
  for (const shot of shots) {
    const actions = (shot.actions ?? []) as Array<Record<string, unknown>>
    for (const action of actions) {
      if (action.type !== 'talk') continue
      const text = String(action.text ?? '').trim()
      if (!text) continue
      const offsetSec = Number(action.start ?? 0)
      const wavPath = resolvePath(tmpdir(), `veraframe-tts-${randomUUID()}.wav`)
      emit({ step: 'tts', detail: `"${text.slice(0, 40)}…"` })
      try {
        const result = await runTts(text, wavPath, repoRoot)
        clips.push({ audioPath: result.output_path, offsetSec })
      } catch (err) {
        // Don't fail the whole render on a TTS error — log and move on.
        console.warn(`[render] TTS failed for action #${index}: ${(err as Error).message}`)
      }
      index += 1
    }
  }
  return clips
}
