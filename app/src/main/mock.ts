import type { AssetRegistry } from './assets'

/**
 * Canned timeline for `--mock`-style rendering — no LLM call.
 *
 * If a second character preset is available, the mock spawns two characters:
 * the student walks toward the centered spawn while the robot idles at a
 * separate spawn point, proving the multi-actor render path. Falls back to a
 * single-character timeline (and ultimately a single idle) when the scene or
 * registry doesn't have the spawn points / animations needed.
 */
export function buildMockTimeline(assets: AssetRegistry, durationSec = 8.0): Record<string, unknown> {
  const sceneId = Object.keys(assets.scenes)[0]
  if (!sceneId) throw new Error('mock: no scenes in registry')
  const scene = assets.scenes[sceneId]
  const characterIds = Object.keys(assets.characters)
  if (characterIds.length === 0) throw new Error('mock: no characters in registry')
  const camera = scene.cameraPresets[0] ?? 'wide'

  const studentPreset = characterIds[0]
  const robotPreset = characterIds[1] ?? null

  const hasWalk = 'walk_in_place' in assets.animations
  const centered = scene.spawnPoints.includes('center_room') ? 'center_room' : null
  const walkStart = scene.spawnPoints.find((s) => s !== centered) ?? null
  // Prefer a third distinct spawn point for the robot so the two characters
  // do not overlap. Falls back to any spawn not used by the student.
  const robotSpawn =
    scene.spawnPoints.find((s) => s !== centered && s !== walkStart) ??
    scene.spawnPoints.find((s) => s !== walkStart) ??
    null

  const characters: Array<Record<string, unknown>> = [
    { id: 'student', preset: studentPreset, spawn: walkStart ?? centered ?? scene.spawnPoints[0] }
  ]
  if (robotPreset && robotSpawn) {
    characters.push({ id: 'robot', preset: robotPreset, spawn: robotSpawn })
  }

  if (hasWalk && centered && walkStart && durationSec >= 3.0) {
    const walkDuration = Math.min(6.0, durationSec * 0.5)
    const actions: Array<Record<string, unknown>> = [
      {
        id: 'a1',
        type: 'walk_to',
        character: 'student',
        target: centered,
        start: 0.0,
        end: walkDuration
      },
      {
        id: 'a2',
        type: 'idle',
        character: 'student',
        start: walkDuration,
        end: durationSec
      }
    ]
    if (robotPreset && robotSpawn) {
      actions.push({
        id: 'a3',
        type: 'idle',
        character: 'robot',
        start: 0.0,
        end: durationSec
      })
    }
    return {
      project: 'mock',
      scene: sceneId,
      characters,
      shots: [
        {
          id: 'shot_001',
          start: 0.0,
          end: durationSec,
          camera,
          actions
        }
      ]
    }
  }

  const spawn = centered ?? scene.spawnPoints[0]
  return {
    project: 'mock',
    scene: sceneId,
    characters: [{ id: 'student', preset: studentPreset, spawn }],
    shots: [
      {
        id: 'shot_001',
        start: 0.0,
        end: durationSec,
        camera,
        actions: [
          {
            id: 'a1',
            type: 'idle',
            character: 'student',
            start: 0.0,
            end: durationSec
          }
        ]
      }
    ]
  }
}
