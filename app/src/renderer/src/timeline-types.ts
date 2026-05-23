/**
 * Renderer-side structural types for a generated Veraframe timeline.
 *
 * These shadow the Pydantic models in `planner/schema.py` at a structural
 * level — we use them for in-renderer manipulations (range edits, take
 * snapshots, etc.) without depending on the full json-schema → TS pipeline.
 * The renderer treats unknown action subtypes as `[key: string]: unknown`
 * so new schema additions don't break the typecheck before regen.
 */

export interface TimelineAction {
  id: string
  type: string
  character?: string
  start: number
  end: number
  [key: string]: unknown
}

export interface TimelineShot {
  id: string
  start: number
  end: number
  camera: string
  actions: TimelineAction[]
}

export interface TimelineCharacter {
  id: string
  preset: string
  spawn: string
}

export interface Timeline {
  scene: string
  characters: TimelineCharacter[]
  shots: TimelineShot[]
}
