/**
 * Pure helpers for serializing/parsing the `.veraframe` project file.
 *
 * The Electron IPC handlers in `index.ts` wrap these with `dialog` +
 * `fs` calls. Keeping the schema logic here means it's exercisable
 * without spinning up a renderer process.
 */

export interface ProjectFileTake {
  id: string
  name: string
  savedAt: string
  timeline: Record<string, unknown>
  renderId: string
  videoUrl: string
  durationSec: number
  prompt: string
}

export interface ProjectFile {
  version: 1
  /** ISO timestamp when this project was saved. */
  savedAt: string
  selectedScene: string | null
  selectedCharacters: string[]
  prompt: string
  mode: 'mock' | 'llm'
  provider: string
  model: string
  /** Optional last-rendered timeline JSON. */
  timeline: Record<string, unknown> | null
  /** Per-project style lock (lighting preset, etc.). Optional for
   *  back-compat with projects saved before this field existed. */
  projectStyle?: {
    lighting?: string
  }
  /** Non-destructive branch snapshots. Optional for back-compat with
   *  projects saved before takes existed; treat absent as []. */
  takes?: ProjectFileTake[]
  /** Action ids the user has approved / locked. Frozen actions guard
   *  the range-edit + full-rerender flows. Optional for back-compat. */
  frozenActionIds?: string[]
  /** Per-project render flags. These ride along so re-rendering an
   *  opened project produces the same flavor of output (voice on, draft
   *  vs hi-fi, foot-lock toggle). Each one optional for back-compat. */
  renderFlags?: {
    quality?: 'draft' | 'hifi'
    generateAudio?: boolean
    physicsPostPass?: boolean
  }
}

export type ProjectFilePayload = Omit<ProjectFile, 'version' | 'savedAt'>

/** Stamp a save-time payload with version + ISO timestamp. */
export function buildProjectFile(payload: ProjectFilePayload, now: Date = new Date()): ProjectFile {
  return {
    version: 1,
    savedAt: now.toISOString(),
    ...payload
  }
}

/** Pretty-printed JSON ready to write to disk. */
export function serializeProjectFile(payload: ProjectFilePayload, now: Date = new Date()): string {
  return JSON.stringify(buildProjectFile(payload, now), null, 2)
}

export type ParseResult =
  | { ok: true; project: ProjectFile }
  | { ok: false; error: string }

/**
 * Parse raw file contents into a ProjectFile.
 * Rejects malformed JSON and unsupported versions. Older files that lack
 * `projectStyle` are accepted unchanged — the renderer defaults it.
 */
export function parseProjectFile(raw: string): ParseResult {
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch (err) {
    return { ok: false, error: (err as Error).message }
  }
  if (!parsed || typeof parsed !== 'object') {
    return { ok: false, error: 'project file is not a JSON object' }
  }
  const candidate = parsed as ProjectFile
  if (candidate.version !== 1) {
    return { ok: false, error: `unsupported project version: ${String(candidate.version)}` }
  }
  return { ok: true, project: candidate }
}
