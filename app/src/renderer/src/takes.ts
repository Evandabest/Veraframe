/**
 * Branch/take snapshots for non-destructive iteration.
 *
 * A `Take` captures the timeline state + the render metadata at the moment
 * the user clicks "Save as Take". Switching to a take restores its timeline
 * into the editor, and — if the corresponding renderId is still in main's
 * `renderedVideos` Map — the video URL too. Across sessions the renderId
 * becomes stale; the UI shows the take's timeline and lets the user re-
 * render to materialize the video again.
 *
 * Takes live inside the .veraframe project file so they survive save/open.
 */

export interface Take {
  /** Stable id (e.g. take_<timestamp>); used as React key + dedup. */
  id: string
  /** Human-friendly label. Defaults to "Take N" but the user can rename. */
  name: string
  /** ISO timestamp when the take was captured. */
  savedAt: string
  /** The full timeline JSON at capture time. */
  timeline: Record<string, unknown>
  /** The render id from main's in-memory video cache. May be stale across
   *  sessions — restoreTake handles that case by leaving videoUrl null. */
  renderId: string
  /** The blob/protocol URL the renderer used (`veraframe-render://...`).
   *  Becomes a broken link once main's cache is cleared, hence the
   *  "needs re-render" affordance in the UI. */
  videoUrl: string
  /** Render duration the take was captured at; used to size the timeline
   *  canvas before any new render. */
  durationSec: number
  /** The prompt that produced this take, if any. Helps the user remember
   *  what they were going for when they look at the list later. */
  prompt: string
}

/**
 * Default name for the Nth take in a list. We avoid reusing existing names
 * to keep the list scannable.
 */
export function defaultTakeName(existing: Take[]): string {
  const used = new Set(existing.map((t) => t.name))
  for (let i = existing.length + 1; ; i += 1) {
    const candidate = `Take ${i}`
    if (!used.has(candidate)) return candidate
  }
}

let _takeIdCounter = 0

/** Generate a new take id. Stable across this session. The counter suffix
 *  guarantees uniqueness even when two captures happen in the same ms. */
export function newTakeId(now: Date = new Date()): string {
  _takeIdCounter = (_takeIdCounter + 1) % 0xffff
  return `take_${now.getTime().toString(36)}_${_takeIdCounter.toString(36)}`
}

export interface CaptureInput {
  timeline: Record<string, unknown>
  renderId: string
  videoUrl: string
  durationSec: number
  prompt: string
}

/** Build a Take snapshot from the current render state. Used by the UI's
 *  "Save as Take" button. */
export function captureTake(
  existing: Take[],
  input: CaptureInput,
  now: Date = new Date()
): Take {
  return {
    id: newTakeId(now),
    name: defaultTakeName(existing),
    savedAt: now.toISOString(),
    timeline: input.timeline,
    renderId: input.renderId,
    videoUrl: input.videoUrl,
    durationSec: input.durationSec,
    prompt: input.prompt
  }
}

/** Apply a rename, returning a new list (so React state updates cleanly). */
export function renameTake(takes: Take[], id: string, name: string): Take[] {
  const trimmed = name.trim()
  if (trimmed === '') return takes
  return takes.map((t) => (t.id === id ? { ...t, name: trimmed } : t))
}

/** Delete a take by id, returning a new list. */
export function deleteTake(takes: Take[], id: string): Take[] {
  return takes.filter((t) => t.id !== id)
}

/** Find a take by id. Returns null if not present. */
export function findTake(takes: Take[], id: string): Take | null {
  return takes.find((t) => t.id === id) ?? null
}
