/**
 * Pure helpers shared by the asset upload / edit IPC handlers.
 *
 * Pulled out of `index.ts` so they can be unit-tested without spinning
 * up Electron dialogs or the file system.
 */

export interface CharacterFileDetection {
  mesh: string | null
  idle: string | null
  walk: string | null
}

/**
 * Given a list of filenames (NOT paths) inside a folder the user picked
 * for a character upload, identify which one is the mesh, the idle clip,
 * and the walk clip. Returns nulls for the slots that couldn't be matched.
 */
export function detectCharacterFiles(filenames: string[]): CharacterFileDetection {
  const fbxFiles = filenames.filter((n) => n.toLowerCase().endsWith('.fbx'))

  const findBy = (predicate: (lower: string) => boolean): string | null => {
    const hit = fbxFiles.find((n) => predicate(n.toLowerCase()))
    return hit ?? null
  }

  const idle = findBy((n) => n === 'idle.fbx') ?? findBy((n) => /(^|[^a-z])idle/.test(n))
  const walk =
    findBy((n) => n === 'walk_in_place.fbx' || n === 'walk.fbx') ??
    findBy((n) => /(^|[^a-z])walk/.test(n))
  const mesh =
    findBy((n) => n === 'character.fbx' || n === 'mesh.fbx') ??
    findBy((n) => !/(^|[^a-z])(idle|walk)/.test(n))

  return { mesh, idle, walk }
}

/**
 * Pick the scene file to use from a folder's filename list. Prefers an
 * exact `scene.blend` / `scene.fbx` match before falling back to any
 * `.blend` / `.fbx` file the user dropped in. Returns null when nothing
 * usable is present.
 */
export function pickSceneFile(filenames: string[]): string | null {
  const candidates = filenames.filter((n) => {
    const lower = n.toLowerCase()
    return lower.endsWith('.blend') || lower.endsWith('.fbx')
  })
  if (candidates.length === 0) return null
  const preferred = candidates.find((n) => /^scene\.(blend|fbx)$/i.test(n))
  return preferred ?? candidates[0]
}

/**
 * Validate a user-provided asset id (the folder name on disk). The
 * planner / daemon read this as a registry key, so we restrict it to
 * filesystem-safe alphanumerics and underscores.
 */
export function isValidAssetId(id: string): boolean {
  return /^[a-z0-9_]+$/i.test(id)
}

/**
 * Derive the on-disk extension to use when copying a user-picked scene
 * file. Only `.fbx` and `.blend` are supported; anything else falls back
 * to `.blend` so the daemon's default loader is used.
 */
export function deriveSceneExtension(sourcePath: string): 'blend' | 'fbx' {
  const sourceExt = sourcePath.toLowerCase().replace(/^.*\./, '')
  return sourceExt === 'fbx' ? 'fbx' : 'blend'
}

export interface SceneManifestInput {
  id: string
  displayName: string
  description?: string
  blendFile: string
  spawnPoints: string[]
  cameraPresets: string[]
  lightingPresets?: string[]
}

/** Build the on-disk `scene.json` body. */
export function buildSceneManifest(input: SceneManifestInput): Record<string, unknown> {
  return {
    id: input.id,
    display_name: input.displayName,
    description: input.description ?? '',
    blend_file: input.blendFile,
    spawn_points: input.spawnPoints,
    camera_presets: input.cameraPresets,
    lighting_presets: input.lightingPresets ?? ['default']
  }
}

export interface CharacterManifestInput {
  id: string
  displayName: string
  description?: string
}

/** Build the on-disk `character.json` body for a newly uploaded character. */
export function buildCharacterManifest(input: CharacterManifestInput): Record<string, unknown> {
  return {
    id: input.id,
    display_name: input.displayName,
    description: input.description ?? '',
    mesh_file: 'character.fbx',
    rig_type: 'mixamo',
    animations: {
      idle: 'idle.fbx',
      walk_in_place: 'walk_in_place.fbx'
    }
  }
}
