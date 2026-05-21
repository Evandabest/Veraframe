import type { AssetRegistry } from './assets'

/** Canned timeline for `--mock`-style rendering — no LLM call. */
export function buildMockTimeline(assets: AssetRegistry, durationSec = 8.0): Record<string, unknown> {
  const sceneId = Object.keys(assets.scenes)[0]
  if (!sceneId) throw new Error('mock: no scenes in registry')
  const scene = assets.scenes[sceneId]
  const characterId = Object.keys(assets.characters)[0]
  if (!characterId) throw new Error('mock: no characters in registry')
  const camera = scene.cameraPresets[0] ?? 'wide'

  const hasWalk = 'walk_in_place' in assets.animations
  const centered = scene.spawnPoints.includes('center_room') ? 'center_room' : null
  const walkStart = scene.spawnPoints.find((s) => s !== centered) ?? null

  if (hasWalk && centered && walkStart && durationSec >= 3.0) {
    const walkDuration = Math.min(6.0, durationSec * 0.5)
    return {
      project: 'mock',
      scene: sceneId,
      characters: [{ id: 'student', preset: characterId, spawn: walkStart }],
      shots: [
        {
          id: 'shot_001',
          start: 0.0,
          end: durationSec,
          camera,
          actions: [
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
        }
      ]
    }
  }

  const spawn = centered ?? scene.spawnPoints[0]
  return {
    project: 'mock',
    scene: sceneId,
    characters: [{ id: 'student', preset: characterId, spawn }],
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
