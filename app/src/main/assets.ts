import { existsSync, readdirSync, readFileSync, statSync } from 'fs'
import { resolve as resolvePath } from 'path'

export interface SceneManifest {
  id: string
  displayName: string
  blendPath: string
  spawnPoints: string[]
  cameraPresets: string[]
}

export interface CharacterManifest {
  id: string
  displayName: string
  meshPath: string
  rigType: string
}

export interface AnimationManifest {
  id: string
  displayName: string
  fbxPath: string
}

export interface AssetRegistry {
  assetsDir: string
  scenes: Record<string, SceneManifest>
  characters: Record<string, CharacterManifest>
  animations: Record<string, AnimationManifest>
}

/**
 * Load all scene/character/animation manifests under `assetsDir`.
 *
 * Mirrors `planner/registry.py` for the parts main needs to drive the daemon:
 * scene blend path, character mesh fbx, and animation fbx paths.
 */
export function loadAssets(assetsDir: string): AssetRegistry {
  return {
    assetsDir,
    scenes: loadGroup<SceneManifest>(resolvePath(assetsDir, 'scenes'), 'scene.json', (raw, dir) => ({
      id: String(raw.id),
      displayName: String(raw.display_name ?? raw.id),
      blendPath: resolvePath(dir, String(raw.blend_file)),
      spawnPoints: (raw.spawn_points ?? []) as string[],
      cameraPresets: (raw.camera_presets ?? []) as string[]
    })),
    characters: loadGroup<CharacterManifest>(
      resolvePath(assetsDir, 'characters'),
      'character.json',
      (raw, dir) => ({
        id: String(raw.id),
        displayName: String(raw.display_name ?? raw.id),
        meshPath: resolvePath(dir, String(raw.mesh_file)),
        rigType: String(raw.rig_type ?? 'mixamo')
      })
    ),
    animations: loadGroup<AnimationManifest>(
      resolvePath(assetsDir, 'animations'),
      'animation.json',
      (raw, dir) => ({
        id: String(raw.id),
        displayName: String(raw.display_name ?? raw.id),
        fbxPath: resolvePath(dir, String(raw.fbx_file))
      })
    )
  }
}

function loadGroup<T extends { id: string }>(
  dir: string,
  manifestName: string,
  parse: (raw: Record<string, unknown>, dir: string) => T
): Record<string, T> {
  const out: Record<string, T> = {}
  if (!existsSync(dir)) return out
  for (const entry of readdirSync(dir)) {
    const sub = resolvePath(dir, entry)
    if (!statSync(sub).isDirectory()) continue
    const manifest = resolvePath(sub, manifestName)
    if (!existsSync(manifest)) continue
    const raw = JSON.parse(readFileSync(manifest, 'utf8')) as Record<string, unknown>
    const parsed = parse(raw, sub)
    out[parsed.id] = parsed
  }
  return out
}

/** Locate the repo's `assets/` directory relative to the running main process. */
export function resolveAssetsDir(): string {
  const candidates = [
    resolvePath(__dirname, '..', '..', '..', 'assets'),
    resolvePath(__dirname, '..', '..', 'assets'),
    resolvePath(process.cwd(), 'assets'),
    resolvePath(process.cwd(), '..', 'assets')
  ]
  for (const candidate of candidates) {
    if (existsSync(candidate)) return candidate
  }
  throw new Error(`Could not locate assets/ directory. Tried:\n${candidates.join('\n')}`)
}
