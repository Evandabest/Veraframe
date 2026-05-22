/**
 * Read-only timeline viewer with click + drag scrubbing.
 *
 * Layout: a two-column flex row. Left column holds aligned lane labels;
 * right column holds the ruler, each lane row, and a full-area pointer
 * overlay that captures scrub gestures. Action blocks and tick labels use
 * `pointer-events-none` so they never swallow events.
 *
 * The red playhead is driven by `currentTimeSec`.
 */

import { Fragment, useRef, useState } from 'react'

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

interface TimelinePanelProps {
  timeline: Record<string, unknown>
  currentTimeSec: number
  durationSec: number
  onSeek?: (timeSec: number) => void
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

function asTimeline(raw: Record<string, unknown>): Timeline {
  return raw as unknown as Timeline
}

export function TimelinePanel({
  timeline,
  currentTimeSec,
  durationSec,
  onSeek
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

  const seconds = Math.max(1, Math.ceil(durationSec))
  const ticks = Array.from({ length: seconds + 1 }, (_, i) => i)

  const scrubRef = useRef<HTMLDivElement | null>(null)
  const [isScrubbing, setIsScrubbing] = useState(false)

  const seekFromClientX = (clientX: number): void => {
    if (!onSeek || !scrubRef.current || durationSec <= 0) return
    const rect = scrubRef.current.getBoundingClientRect()
    const ratio = (clientX - rect.left) / rect.width
    onSeek(Math.max(0, Math.min(durationSec, ratio * durationSec)))
  }

  const onPointerDown = (event: React.PointerEvent<HTMLDivElement>): void => {
    event.preventDefault()
    event.currentTarget.setPointerCapture(event.pointerId)
    setIsScrubbing(true)
    seekFromClientX(event.clientX)
  }

  const onPointerMove = (event: React.PointerEvent<HTMLDivElement>): void => {
    if (!isScrubbing) return
    seekFromClientX(event.clientX)
  }

  const stopScrubbing = (event: React.PointerEvent<HTMLDivElement>): void => {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId)
    }
    setIsScrubbing(false)
  }

  const playheadPct = durationSec > 0 ? (currentTimeSec / durationSec) * 100 : 0

  return (
    <div className="flex flex-col gap-2 rounded-lg border border-neutral-800 bg-neutral-900 p-3">
      <div className="flex items-baseline justify-between">
        <h2 className="text-sm font-semibold text-neutral-200">Timeline</h2>
        <span className="text-xs text-neutral-500">
          scene: <span className="text-neutral-300">{tl.scene}</span> · {actions.length} action
          {actions.length === 1 ? '' : 's'} · {durationSec.toFixed(1)}s · click or drag to scrub
        </span>
      </div>

      <div className="flex gap-2">
        {/* Left: aligned lane labels */}
        <div className="flex w-24 flex-shrink-0 flex-col gap-1">
          <div className="h-5" /> {/* spacer aligned with ruler */}
          {lanes.map((lane) => (
            <div
              key={`label-${lane.id}`}
              className="flex h-8 items-center text-xs text-neutral-400"
            >
              {lane.label}
            </div>
          ))}
        </div>

        {/* Right: ruler + lane rows + scrub overlay + playhead */}
        <div className="relative flex-1">
          <div className="flex flex-col gap-1">
            {/* Ruler — tick line and label are separate elements so the label
              for the rightmost tick can sit FLUSH-LEFT of its line (with a
              translateX(-100%)) instead of overflowing the container. */}
            <div className="pointer-events-none relative h-5 overflow-hidden border-b border-neutral-800">
              {ticks.map((t) => {
                const leftPct = (t / durationSec) * 100
                const isLast = t === ticks[ticks.length - 1]
                return (
                  <Fragment key={t}>
                    <div
                      className="absolute top-0 h-full w-px bg-neutral-800"
                      style={{ left: `${leftPct}%` }}
                    />
                    <div
                      className="absolute top-0 text-[10px] text-neutral-500"
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

            {/* Lane rows */}
            {lanes.length === 0 && (
              <p className="text-sm text-neutral-500">No actions in this timeline.</p>
            )}
            {lanes.map((lane) => (
              <div
                key={lane.id}
                className="pointer-events-none relative h-8 rounded bg-neutral-950/60"
              >
                {lane.actions.map((action) => {
                  const left = (action.start / durationSec) * 100
                  const width = ((action.end - action.start) / durationSec) * 100
                  const [bg, border] = ACTION_COLORS[action.type] ?? DEFAULT_COLORS
                  return (
                    <div
                      key={action.id}
                      title={`${action.type} (${action.start.toFixed(1)}s–${action.end.toFixed(1)}s)`}
                      className={`pointer-events-none absolute top-1 h-6 overflow-hidden rounded border ${bg} ${border} px-1 text-[10px] leading-6 text-white`}
                      style={{ left: `${left}%`, width: `${Math.max(width, 0.5)}%` }}
                    >
                      {action.type}
                    </div>
                  )
                })}
              </div>
            ))}
          </div>

          {/* Scrub overlay — full area of the right column. Sits ABOVE the
              lanes (z-10) so the pointer-events-none action blocks never
              swallow gestures. */}
          <div
            ref={scrubRef}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={stopScrubbing}
            onPointerCancel={stopScrubbing}
            className={`absolute inset-0 z-10 ${isScrubbing ? 'cursor-grabbing' : 'cursor-pointer'}`}
            style={{ touchAction: 'none' }}
          />

          {/* Playhead — above lanes but pointer-events-none so the overlay
              still receives gestures right under it. */}
          <div
            className="pointer-events-none absolute inset-y-0 z-20 w-px bg-red-400"
            style={{ left: `${playheadPct}%` }}
          />
        </div>
      </div>
    </div>
  )
}
