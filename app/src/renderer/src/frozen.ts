/**
 * Action-freeze helpers (Step 49 — region/shot retake with frozen blocks).
 *
 * Users mark individual actions as "approved" (visually a lock icon on
 * the action block). Frozen actions guard the range-edit + full-render
 * flows: anything that *would* mutate a frozen action is either refused
 * or routed around. Freeze state lives entirely renderer-side — it's
 * never sent to the LLM and never persisted in the timeline JSON itself.
 * It's serialized as `frozenActionIds: string[]` in the .veraframe file
 * so freezes survive save/open.
 */

import type { TimelineAction } from './timeline-types'

export interface RangeWindow {
  start: number
  end: number
}

/** Toggle membership in the frozen set, returning a new array. */
export function toggleFrozen(frozen: readonly string[], actionId: string): string[] {
  const set = new Set(frozen)
  if (set.has(actionId)) set.delete(actionId)
  else set.add(actionId)
  return Array.from(set)
}

export function isFrozen(frozen: readonly string[], actionId: string): boolean {
  return frozen.includes(actionId)
}

/**
 * Return the frozen actions that overlap a time window. Used by the
 * range-edit submit guard: if any frozen action overlaps the window
 * the user has selected, we refuse to call the LLM.
 *
 * Overlap here is "any time-overlap", not "fully inside" — even an
 * action that straddles the window boundary needs to be flagged
 * because the user clearly indicated the range covers part of it.
 */
export function frozenInWindow(
  actions: TimelineAction[],
  frozen: readonly string[],
  window: RangeWindow
): TimelineAction[] {
  const set = new Set(frozen)
  return actions.filter((a) => {
    if (!set.has(a.id)) return false
    // Time overlap.
    return a.end > window.start && a.start < window.end
  })
}
