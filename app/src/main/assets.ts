import { existsSync, readdirSync, readFileSync, statSync } from 'fs'
import { resolve as resolvePath } from 'path'

export interface SceneManifest {
  id: string
  displayName: string
  blendPath: string
  spawnPoints: string[]
  cameraPresets: string[]
  lightingPresets: string[]
}

export interface CharacterManifest {
  id: string
  displayName: string
  meshPath: string
  rigType: string
  /** Per-character animation FBX paths. Keys match the global animation ids
   *  the executor expects ("idle", "walk_in_place", etc.). When non-empty
   *  these override the global animations registry for this character. */
  animations: Record<string, string>
  /** Free-form bio shown in the Library and folded into the LLM system
   *  prompt so the model can reason about the character ("anxious lab
   *  student"). Empty string when unset. */
  description: string
  /** Default Emotion (one of: neutral, joy, angry, sorrow, fun) applied
   *  to walk_to / idle when the LLM doesn't pick one. Empty string = none. */
  defaultEmotion: string
  /** TTS voice override. Maps to `--voice` on `planner.run_tts`. Empty
   *  string falls back to the project-wide default. */
  voice: string
}

export interface AnimationManifest {
  id: string
  displayName: string
  fbxPath: string
}

export interface MotionClipManifest {
  id: string
  displayName: string
  description: string
  fbxPath: string
  appliesToRig: string
}

export interface AssetRegistry {
  /** Primary (repo-bundled) assets directory. */
  assetsDir: string
  /** User-data directory where uploaded assets are stored. May be empty. */
  userAssetsDir?: string
  scenes: Record<string, SceneManifest>
  characters: Record<string, CharacterManifest>
  animations: Record<string, AnimationManifest>
  /** User-supplied motion clips for the `play_clip` action. Step 51 — Option C. */
  motions: Record<string, MotionClipManifest>
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
      cameraPresets: (raw.camera_presets ?? []) as string[],
      lightingPresets: (raw.lighting_presets ?? []) as string[]
    }))
  const scanCharacters = (dir: string): Record<string, CharacterManifest> =>
    loadGroup<CharacterManifest>(
      resolvePath(dir, 'characters'),
      'character.json',
      (raw, d) => {
        const rawAnims = (raw.animations ?? {}) as Record<string, unknown>
        const animations: Record<string, string> = {}
        for (const [k, v] of Object.entries(rawAnims)) {
          if (typeof v === 'string' && v.length > 0) animations[k] = resolvePath(d, v)
        }
        return {
          id: String(raw.id),
          displayName: String(raw.display_name ?? raw.id),
          meshPath: resolvePath(d, String(raw.mesh_file)),
          rigType: String(raw.rig_type ?? 'mixamo'),
          animations,
          description: typeof raw.description === 'string' ? raw.description : '',
          defaultEmotion:
            typeof raw.default_emotion === 'string' ? raw.default_emotion : '',
          voice: typeof raw.voice === 'string' ? raw.voice : ''
        }
      }
    )
  const scanMotions = (dir: string): Record<string, MotionClipManifest> =>
    loadGroup<MotionClipManifest>(
      resolvePath(dir, 'motions'),
      'motion.json',
      (raw, d) => ({
        id: String(raw.id),
        displayName: String(raw.display_name ?? raw.id),
        description: typeof raw.description === 'string' ? raw.description : '',
        fbxPath: resolvePath(d, String(raw.fbx_file)),
        appliesToRig: String(raw.applies_to_rig ?? 'mixamo')
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
    },
    motions: {
      ...scanMotions(assetsDir),
      ...(userAssetsDir ? scanMotions(userAssetsDir) : {})
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
