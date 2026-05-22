/**
 * Read-only timeline viewer with click + drag scrubbing, click-to-edit
 * blocks, and a "+" button at the end of each lane to add new actions.
 *
 * Layout
 * ------
 * Left column = aligned lane labels.
 * Right column = ruler + one row per lane.
 *
 * Each lane row has its OWN pointer handlers (no unified scrub overlay) so
 * the same gesture can mean different things depending on where it lands:
 *
 *   - quick tap (pointer barely moved) on an action block → onEditAction
 *   - quick tap on empty lane space → seek to that time (onSeek)
 *   - drag → scrub-seek, captured to the lane that received pointerdown so
 *           the drag continues even when the cursor moves to another lane
 *
 * The playhead is driven by `requestAnimationFrame` reading
 * `video.currentTime` directly (60Hz, GPU-composited transform) instead of
 * React state — `timeupdate` only fires ~4-15Hz.
 *
 * When a pending edit exists, the original block is rendered faded and the
 * replacement is rendered on top with a green outline so the user can
 * visually diff before accepting.
 */

import { Fragment, useEffect, useRef, useState, type RefObject } from 'react'

interface TimelineAction {
  id: string
  type: string
  character?: string
  start: number
  end: number
  [key: string]: unknown
}

interface TimelineShot {
  id: string
  start: number
  end: number
  actions: TimelineAction[]
}

interface TimelineCharacter {
  id: string
  preset: string
  spawn: string
}

interface Timeline {
  scene: string
  characters: TimelineCharacter[]
  shots: TimelineShot[]
}

export interface PendingActionEdit {
  /** ID of the action being replaced, OR null for an entirely new action. */
  originalActionId: string | null
  newAction: TimelineAction
  /** Lane (character handle) this new action belongs to. */
  laneId: string
}

interface TimelinePanelProps {
  timeline: Record<string, unknown>
  videoRef: RefObject<HTMLVideoElement | null>
  durationSec: number
  onSeek?: (timeSec: number) => void
  onEditAction?: (action: TimelineAction, laneId: string) => void
  onAddAction?: (laneId: string, startSec: number) => void
  onAddCharacter?: () => void
  pendingEdit?: PendingActionEdit | null
}

const SCENE_LANE_ID = '__scene__'
const SCENE_ACTION_TYPES = new Set(['camera_cut', 'camera_dolly', 'set_lighting'])

const ACTION_COLORS: Record<string, [string, string]> = {
  walk_to: ['bg-blue-600/70', 'border-blue-400'],
  turn_to: ['bg-blue-500/60', 'border-blue-400'],
  idle: ['bg-neutral-600/70', 'border-neutral-400'],
  sit: ['bg-indigo-600/70', 'border-indigo-400'],
  stand: ['bg-indigo-500/60', 'border-indigo-400'],
  look_at: ['bg-amber-600/70', 'border-amber-400'],
  point_at: ['bg-amber-500/60', 'border-amber-400'],
  smile: ['bg-pink-600/70', 'border-pink-400'],
  frown: ['bg-pink-500/60', 'border-pink-400'],
  blink: ['bg-pink-500/40', 'border-pink-400'],
  talk: ['bg-purple-600/70', 'border-purple-400'],
  camera_cut: ['bg-cyan-600/70', 'border-cyan-400'],
  camera_dolly: ['bg-cyan-500/60', 'border-cyan-400'],
  set_lighting: ['bg-yellow-600/70', 'border-yellow-400']
}
const DEFAULT_COLORS: [string, string] = ['bg-neutral-700/70', 'border-neutral-500']

const CLICK_THRESHOLD_PX_SQ = 16 // 4px in any direction still counts as a click

function asTimeline(raw: Record<string, unknown>): Timeline {
  return raw as unknown as Timeline
}

export function TimelinePanel({
  timeline,
  videoRef,
  durationSec,
  onSeek,
  onEditAction,
  onAddAction,
  onAddCharacter,
  pendingEdit
}: TimelinePanelProps): React.JSX.Element {
  const tl = asTimeline(timeline)
  const actions = tl.shots?.flatMap((s) => s.actions) ?? []
  const characters = tl.characters ?? []

  const lanes: Array<{ id: string; label: string; actions: TimelineAction[] }> = []
  for (const c of characters) {
    lanes.push({
      id: c.id,
      label: c.id,
      actions: actions.filter((a) => a.character === c.id)
    })
  }
  const sceneActions = actions.filter((a) => SCENE_ACTION_TYPES.has(a.type))
  if (sceneActions.length > 0) {
    lanes.push({ id: SCENE_LANE_ID, label: 'scene', actions: sceneActions })
  }

  // `durationSec` is the rendered video's length. `displayDuration` is the
  // width of the timeline canvas — wider than the video when a pending edit
  // extends past the current end so the new block is actually visible.
  const pendingExtension =
    pendingEdit && pendingEdit.newAction.end > durationSec ? pendingEdit.newAction.end : 0
  const lastLaneEnd = Math.max(
    0,
    ...lanes.flatMap((l) => l.actions.map((a) => a.end))
  )
  const displayDuration = Math.max(durationSec, lastLaneEnd, pendingExtension)

  const seconds = Math.max(1, Math.ceil(displayDuration))
  const ticks = Array.from({ length: seconds + 1 }, (_, i) => i)

  // Refs for the rAF playhead loop and click/drag bookkeeping.
  const contentRef = useRef<HTMLDivElement | null>(null)
  const playheadRef = useRef<HTMLDivElement | null>(null)
  const pointerStartRef = useRef<{ x: number; y: number; t: number } | null>(null)
  const isDraggingRef = useRef(false)
  const isScrubbingRef = useRef(false)
  const lastPointerXRef = useRef(0)
  const [scrubbingCursor, setScrubbingCursor] = useState(false)

  // Drive the playhead at the display refresh rate. While scrubbing, follow
  // the cursor directly so the line never lags. Otherwise read currentTime.
  useEffect(() => {
    let rafId = 0
    const tick = (): void => {
      const playhead = playheadRef.current
      const content = contentRef.current
      if (playhead && content && displayDuration > 0) {
        const rect = content.getBoundingClientRect()
        let pct: number
        if (isScrubbingRef.current && isDraggingRef.current) {
          pct = (lastPointerXRef.current - rect.left) / rect.width
        } else {
          const video = videoRef.current
          // displayDuration may be larger than the actual video (pending
          // extension). Playhead reads currentTime relative to displayDuration
          // so it visually stops at videoDuration / displayDuration — making
          // the "unrendered" tail beyond it visually clear.
          pct = video ? video.currentTime / displayDuration : 0
        }
        const clamped = Math.max(0, Math.min(1, pct))
        playhead.style.transform = `translate3d(${clamped * rect.width}px, 0, 0)`
      }
      rafId = requestAnimationFrame(tick)
    }
    rafId = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(rafId)
  }, [displayDuration, videoRef])

  const seekFromClientX = (clientX: number): void => {
    if (!onSeek || !contentRef.current || displayDuration <= 0) return
    const rect = contentRef.current.getBoundingClientRect()
    const ratio = (clientX - rect.left) / rect.width
    // Time is computed against displayDuration but clamped to videoDuration so
    // the user can't seek into the (not-yet-rendered) extension area.
    const timeSec = Math.max(0, Math.min(durationSec, ratio * displayDuration))
    onSeek(timeSec)
  }

  /** Resolve a click on a lane: if it landed inside an action block, edit
   * that block; otherwise treat it as a seek. */
  const resolveLaneClick = (
    lane: { id: string; actions: TimelineAction[] },
    clientX: number,
    rect: DOMRect
  ): void => {
    const ratio = (clientX - rect.left) / rect.width
    const timeSec = Math.max(0, Math.min(displayDuration, ratio * displayDuration))
    const hit = lane.actions.find((a) => timeSec >= a.start && timeSec < a.end)
    if (hit && onEditAction) {
      onEditAction(hit, lane.id)
    } else if (onSeek) {
      // Clamp seek to videoDuration; clicks past the video end snap to the end.
      onSeek(Math.min(timeSec, durationSec))
    }
  }

  // Per-lane handlers. We use pointer capture so a drag started inside one
  // lane keeps firing pointermove on that lane even after the cursor moves
  // away — scrub continues smoothly across the whole timeline.
  const makeLaneHandlers = (
    lane: { id: string; actions: TimelineAction[] }
  ): {
    onPointerDown: (e: React.PointerEvent<HTMLDivElement>) => void
    onPointerMove: (e: React.PointerEvent<HTMLDivElement>) => void
    onPointerUp: (e: React.PointerEvent<HTMLDivElement>) => void
    onPointerCancel: (e: React.PointerEvent<HTMLDivElement>) => void
  } => {
    return {
      onPointerDown: (event) => {
        event.preventDefault()
        event.currentTarget.setPointerCapture(event.pointerId)
        pointerStartRef.current = { x: event.clientX, y: event.clientY, t: Date.now() }
        isDraggingRef.current = false
        isScrubbingRef.current = true
        lastPointerXRef.current = event.clientX
        setScrubbingCursor(true)
      },
      onPointerMove: (event) => {
        if (!isScrubbingRef.current) return
        const start = pointerStartRef.current
        if (!isDraggingRef.current && start) {
          const dx = event.clientX - start.x
          const dy = event.clientY - start.y
          if (dx * dx + dy * dy > CLICK_THRESHOLD_PX_SQ) {
            isDraggingRef.current = true
            seekFromClientX(start.x)
          }
        }
        if (isDraggingRef.current) {
          lastPointerXRef.current = event.clientX
          seekFromClientX(event.clientX)
        }
      },
      onPointerUp: (event) => {
        if (event.currentTarget.hasPointerCapture(event.pointerId)) {
          event.currentTarget.releasePointerCapture(event.pointerId)
        }
        const wasDrag = isDraggingRef.current
        isScrubbingRef.current = false
        isDraggingRef.current = false
        setScrubbingCursor(false)
        if (!wasDrag) {
          const rect = event.currentTarget.getBoundingClientRect()
          resolveLaneClick(lane, event.clientX, rect)
        }
        pointerStartRef.current = null
      },
      onPointerCancel: (event) => {
        if (event.currentTarget.hasPointerCapture(event.pointerId)) {
          event.currentTarget.releasePointerCapture(event.pointerId)
        }
        isScrubbingRef.current = false
        isDraggingRef.current = false
        setScrubbingCursor(false)
        pointerStartRef.current = null
      }
    }
  }

  // Ruler is also clickable for seek (no actions to hit there).
  const onRulerPointerUp = (event: React.PointerEvent<HTMLDivElement>): void => {
    seekFromClientX(event.clientX)
  }

  // Compute the start time for a lane's "+" button. Lives in its own
  // gutter column (right of the lane content), so we don't need an X
  // position — just where in the timeline a new action should start. If the
  // lane has trailing room before durationSec, fill that; otherwise start at
  // the current end and the timeline will extend on accept.
  const addButtonStart = (lane: { id: string; actions: TimelineAction[] }): {
    startSec: number
    extending: boolean
  } | null => {
    if (!onAddAction) return null
    const lastEnd = lane.actions.reduce((acc, a) => Math.max(acc, a.end), 0)
    const startSec = Math.max(lastEnd, durationSec)
    const extending = startSec >= durationSec - 0.05
    return { startSec, extending }
  }

  return (
    <div className="flex flex-col gap-2 rounded-lg border border-neutral-800 bg-neutral-900 p-3">
      <div className="flex items-baseline justify-between">
        <h2 className="text-sm font-semibold text-neutral-200">Timeline</h2>
        <div className="text-xs text-neutral-500">
          scene: <span className="text-neutral-300">{tl.scene}</span> · {actions.length} action
          {actions.length === 1 ? '' : 's'} · {durationSec.toFixed(1)}s
        </div>
      </div>

      <div className="flex gap-2">
        {/* Left: aligned lane labels + the "+ Character" button at the bottom
            of this column so it sits directly under the character names. */}
        <div className="flex w-24 flex-shrink-0 flex-col gap-1">
          <div className="h-5" /> {/* ruler spacer */}
          {lanes.map((lane) => (
            <div
              key={`label-${lane.id}`}
              className="flex h-8 items-center text-xs text-neutral-400"
            >
              {lane.label}
            </div>
          ))}
          {onAddCharacter && (
            <button
              type="button"
              onClick={onAddCharacter}
              title="Add another character (coming soon)"
              className="mt-1 flex h-7 w-full items-center justify-center rounded border border-emerald-500 bg-emerald-500/15 text-base font-medium text-emerald-200 transition-colors hover:bg-emerald-500/30"
            >
              +
            </button>
          )}
        </div>

        {/* Right: ruler + lane rows + playhead */}
        <div ref={contentRef} className="relative flex-1">
          <div className="flex flex-col gap-1">
            {/* Ruler */}
            <div
              onPointerUp={onRulerPointerUp}
              className="relative h-5 cursor-pointer overflow-hidden border-b border-neutral-800"
              style={{ touchAction: 'none' }}
            >
              {ticks.map((t) => {
                const leftPct = (t / displayDuration) * 100
                const isLast = t === ticks[ticks.length - 1]
                return (
                  <Fragment key={t}>
                    <div
                      className="pointer-events-none absolute top-0 h-full w-px bg-neutral-800"
                      style={{ left: `${leftPct}%` }}
                    />
                    <div
                      className="pointer-events-none absolute top-0 text-[10px] text-neutral-500"
                      style={{
                        left: `${leftPct}%`,
                        transform: isLast ? 'translateX(-100%)' : undefined,
                        paddingLeft: isLast ? 0 : 4,
                        paddingRight: isLast ? 4 : 0
                      }}
                    >
                      {t}s
                    </div>
                  </Fragment>
                )
              })}
            </div>

            {/* Lane rows — no per-row + buttons here; they live in the
                rightmost gutter column so they never overflow the canvas. */}
            {lanes.length === 0 && (
              <p className="text-sm text-neutral-500">No actions in this timeline.</p>
            )}
            {lanes.map((lane) => {
              const handlers = makeLaneHandlers(lane)
              const pendingForLane = pendingEdit?.laneId === lane.id ? pendingEdit : null
              return (
                <div
                  key={lane.id}
                  {...handlers}
                  className={`relative h-8 rounded bg-neutral-950/60 ${scrubbingCursor ? 'cursor-grabbing' : 'cursor-pointer'}`}
                  style={{ touchAction: 'none' }}
                >
                  {/* Subtle "extension area" shading past the current video
                      end so the user knows that region isn't rendered yet. */}
                  {displayDuration > durationSec && (
                    <div
                      className="pointer-events-none absolute inset-y-0 rounded-r bg-emerald-500/5"
                      style={{
                        left: `${(durationSec / displayDuration) * 100}%`,
                        right: 0
                      }}
                    />
                  )}

                  {/* Existing action blocks (purely visual — clicks resolved
                      by the lane's pointer handlers above). */}
                  {lane.actions.map((action) => {
                    const left = (action.start / displayDuration) * 100
                    const width = ((action.end - action.start) / displayDuration) * 100
                    const [bg, border] = ACTION_COLORS[action.type] ?? DEFAULT_COLORS
                    const isBeingReplaced = pendingForLane?.originalActionId === action.id
                    return (
                      <div
                        key={action.id}
                        title={`${action.type} (${action.start.toFixed(1)}s–${action.end.toFixed(1)}s) — click to edit`}
                        className={`pointer-events-none absolute top-1 h-6 overflow-hidden rounded border ${bg} ${border} px-1 text-[10px] leading-6 text-white transition-opacity ${isBeingReplaced ? 'opacity-30' : ''}`}
                        style={{ left: `${left}%`, width: `${Math.max(width, 0.5)}%` }}
                      >
                        {action.type}
                      </div>
                    )
                  })}

                  {/* Pending edit preview — overlaid on top of the original
                      with a thick emerald ring so the user can compare. */}
                  {pendingForLane && (() => {
                    const newAction = pendingForLane.newAction
                    const left = (newAction.start / displayDuration) * 100
                    const width = ((newAction.end - newAction.start) / displayDuration) * 100
                    const [bg] = ACTION_COLORS[newAction.type] ?? DEFAULT_COLORS
                    return (
                      <div
                        title={`pending ${newAction.type} (${newAction.start.toFixed(1)}s–${newAction.end.toFixed(1)}s)`}
                        className={`pointer-events-none absolute top-1 h-6 overflow-hidden rounded border-2 border-emerald-400 ${bg} px-1 text-[10px] font-semibold leading-6 text-white shadow-[0_0_0_2px_rgba(16,185,129,0.25)]`}
                        style={{ left: `${left}%`, width: `${Math.max(width, 0.5)}%` }}
                      >
                        {newAction.type}
                      </div>
                    )
                  })()}
                </div>
              )
            })}
          </div>

          {/* Playhead, driven by rAF in useEffect above. */}
          <div
            ref={playheadRef}
            className="pointer-events-none absolute inset-y-0 left-0 z-20 w-px bg-red-400"
            style={{ willChange: 'transform' }}
          />
        </div>

        {/* Right gutter: per-lane "+" buttons, vertically aligned with their
            lane rows. Lives outside the timeline canvas so it never overflows
            the right edge. */}
        <div className="flex w-8 flex-shrink-0 flex-col gap-1">
          <div className="h-5" /> {/* ruler spacer */}
          {lanes.map((lane) => {
            const addBtn = addButtonStart(lane)
            return (
              <div key={`add-${lane.id}`} className="flex h-8 items-center justify-center">
                {addBtn && (
                  <button
                    type="button"
                    onClick={() => onAddAction?.(lane.id, addBtn.startSec)}
                    title={
                      addBtn.extending
                        ? `Extend timeline past ${durationSec.toFixed(1)}s`
                        : `Add action at ${addBtn.startSec.toFixed(1)}s`
                    }
                    className={`flex h-6 w-6 items-center justify-center rounded border text-sm transition-colors ${
                      addBtn.extending
                        ? 'border-emerald-500 bg-emerald-500/20 text-emerald-200 hover:bg-emerald-500/40'
                        : 'border-dashed border-neutral-500 bg-neutral-900/80 text-neutral-300 hover:border-neutral-300 hover:text-white'
                    }`}
                  >
                    +
                  </button>
                )}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
