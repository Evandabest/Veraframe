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
  /** Primary (repo-bundled) assets directory. */
  assetsDir: string
  /** User-data directory where uploaded assets are stored. May be empty. */
  userAssetsDir?: string
  scenes: Record<string, SceneManifest>
  characters: Record<string, CharacterManifest>
  animations: Record<string, AnimationManifest>
}

/**
 * Load all scene/character/animation manifests, merging the repo-bundled
 * `assetsDir` with an optional `userAssetsDir` (typically Electron's
 * `app.getPath('userData')/assets`). User-provided entries override
 * repo entries when their `id` collides.
 *
 * Mirrors `planner/registry.py` for the parts main needs to drive the daemon:
 * scene blend path, character mesh fbx, and animation fbx paths.
 */
export function loadAssets(assetsDir: string, userAssetsDir?: string): AssetRegistry {
  const scanScenes = (dir: string): Record<string, SceneManifest> =>
    loadGroup<SceneManifest>(resolvePath(dir, 'scenes'), 'scene.json', (raw, d) => ({
      id: String(raw.id),
      displayName: String(raw.display_name ?? raw.id),
      blendPath: resolvePath(d, String(raw.blend_file)),
      spawnPoints: (raw.spawn_points ?? []) as string[],
      cameraPresets: (raw.camera_presets ?? []) as string[]
    }))
  const scanCharacters = (dir: string): Record<string, CharacterManifest> =>
    loadGroup<CharacterManifest>(
      resolvePath(dir, 'characters'),
      'character.json',
      (raw, d) => ({
        id: String(raw.id),
        displayName: String(raw.display_name ?? raw.id),
        meshPath: resolvePath(d, String(raw.mesh_file)),
        rigType: String(raw.rig_type ?? 'mixamo')
      })
    )
  const scanAnimations = (dir: string): Record<string, AnimationManifest> =>
    loadGroup<AnimationManifest>(
      resolvePath(dir, 'animations'),
      'animation.json',
      (raw, d) => ({
        id: String(raw.id),
        displayName: String(raw.display_name ?? raw.id),
        fbxPath: resolvePath(d, String(raw.fbx_file))
      })
    )

  return {
    assetsDir,
    userAssetsDir,
    scenes: { ...scanScenes(assetsDir), ...(userAssetsDir ? scanScenes(userAssetsDir) : {}) },
    characters: {
      ...scanCharacters(assetsDir),
      ...(userAssetsDir ? scanCharacters(userAssetsDir) : {})
    },
    animations: {
      ...scanAnimations(assetsDir),
      ...(userAssetsDir ? scanAnimations(userAssetsDir) : {})
    }
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
