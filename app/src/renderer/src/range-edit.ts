/**
 * Pure timeline-merge helpers for natural-language range edits.
 *
 * When the user selects a time window on the timeline and asks the LLM
 * to rewrite that segment, the LLM returns a fresh list of actions for
 * that window. `mergeRangeEdit` swaps those into the existing timeline:
 *
 *   - actions whose [start, end] sits entirely inside the window are
 *     removed (the LLM's new list replaces them);
 *   - actions whose [start, end] sits entirely outside the window are
 *     kept untouched;
 *   - actions that cross a window boundary are kept untouched — the
 *     user explicitly limited the edit scope to the inner window;
 *   - the new actions get inserted into whichever shot owns the window.
 *
 * No re-timing of outside actions, no shot reorganization beyond
 * appending the new actions to the containing shot's `actions` array.
 * Renderer's incremental-render machinery handles the actual splice.
 */

import type { Timeline, TimelineAction, TimelineShot } from './timeline-types'

export interface RangeWindow {
  start: number
  end: number
}

export interface RangeMergeResult {
  timeline: Timeline
  /** Ids of actions removed from the original timeline. */
  removed: string[]
  /** Ids of actions inserted from the new list. */
  inserted: string[]
}

/** Actions whose entire [start, end] lies strictly inside the window. */
export function actionsInsideWindow(actions: TimelineAction[], w: RangeWindow): TimelineAction[] {
  return actions.filter((a) => a.start >= w.start && a.end <= w.end)
}

/**
 * Pick the shot that contains the window. The window must fit within a
 * single shot to be edited atomically. Returns the shot's index in
 * `timeline.shots`, or -1 when the window spans / falls outside shots.
 */
export function findContainingShotIndex(timeline: Timeline, w: RangeWindow): number {
  const shots = timeline.shots ?? []
  for (let i = 0; i < shots.length; i += 1) {
    const s = shots[i]
    if (w.start >= s.start && w.end <= s.end) return i
  }
  return -1
}

/**
 * Swap the actions inside `window` for `newActions`. Returns a new
 * Timeline plus the ids that were removed / inserted for telemetry.
 */
export function mergeRangeEdit(
  timeline: Timeline,
  window: RangeWindow,
  newActions: TimelineAction[]
): RangeMergeResult {
  if (window.end <= window.start) {
    throw new Error(`invalid window: end (${window.end}) must be > start (${window.start})`)
  }
  const shotIdx = findContainingShotIndex(timeline, window)
  if (shotIdx === -1) {
    throw new Error(
      `range edit window ${window.start}-${window.end}s does not fit inside any single shot`
    )
  }

  const out: Timeline = {
    ...timeline,
    shots: timeline.shots.map((s, i) => (i === shotIdx ? rewriteShot(s, window, newActions) : s))
  }
  const removed = actionsInsideWindow(timeline.shots[shotIdx].actions, window).map((a) => a.id)
  const inserted = newActions.map((a) => a.id)
  return { timeline: out, removed, inserted }
}

function rewriteShot(
  shot: TimelineShot,
  w: RangeWindow,
  newActions: TimelineAction[]
): TimelineShot {
  const kept = shot.actions.filter((a) => a.start < w.start || a.end > w.end)
  return { ...shot, actions: [...kept, ...newActions].sort((a, b) => a.start - b.start) }
}
