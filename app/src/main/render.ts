import { randomUUID } from 'crypto'
import { tmpdir } from 'os'
import { resolve as resolvePath } from 'path'
import type { DaemonHandle } from './daemon'
import type { AssetRegistry } from './assets'

export interface RenderProgress {
  step: string
  detail?: string
}

export interface RenderOptions {
  fps?: number
  onProgress?: (event: RenderProgress) => void
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

  const endFrame = Math.round(durationSec * fps)
  emit({ step: 'render', detail: `${endFrame + 1} frame(s)` })
  await daemon.call('render', {
    start_frame: 0,
    end_frame: endFrame,
    output_path: outputPath,
    fps
  })

  return {
    renderId,
    videoPath: outputPath,
    durationSec,
    executed: execResult.executed.length,
    skipped: execResult.skipped.length,
    timeline
  }
}
