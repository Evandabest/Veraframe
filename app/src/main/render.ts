import { randomUUID } from 'crypto'
import { unlink } from 'fs/promises'
import { tmpdir } from 'os'
import { resolve as resolvePath } from 'path'
import type { DaemonHandle } from './daemon'
import type { AssetRegistry } from './assets'
import { ffmpegAppend, ffmpegSplice } from './ffmpeg'

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

export interface RenderOptions {
  fps?: number
  onProgress?: (event: RenderProgress) => void
  incremental?: IncrementalRender
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
  }

  emit({ step: 'execute_timeline' })
  const execResult = (await daemon.call('execute_timeline', {
    timeline,
    asset_paths: assetPaths,
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
      fps
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
    emit({ step: 'render', detail: `${endFrame + 1} frame(s)` })
    await daemon.call('render', {
      start_frame: 0,
      end_frame: endFrame,
      output_path: outputPath,
      fps
    })
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
