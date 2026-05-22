/**
 * Read-only timeline viewer with click + drag scrubbing.
 *
 * The red playhead is driven by `requestAnimationFrame` reading the video
 * element's `currentTime` directly — NOT by React state. The HTML5
 * `timeupdate` event fires only ~4-15Hz, so a state-driven playhead lurches
 * in visible chunks. The rAF loop pushes a transform onto the playhead's DOM
 * node at the display refresh rate (typically 60fps).
 *
 * During a scrub gesture (`isScrubbingRef.current === true`), the playhead
 * follows the pointer's last known X directly instead of waiting for the
 * video to seek — that way it never lags the cursor by a frame or two.
 *
 * Action blocks and tick labels use `pointer-events-none` so the full-area
 * scrub overlay above them always receives clicks and drags.
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

interface TimelinePanelProps {
  timeline: Record<string, unknown>
  videoRef: RefObject<HTMLVideoElement | null>
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
  videoRef,
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
  const playheadRef = useRef<HTMLDivElement | null>(null)
  const isScrubbingRef = useRef(false)
  const lastPointerXRef = useRef(0)
  const [scrubbingCursor, setScrubbingCursor] = useState(false)

  // 60fps playhead loop. Reads video.currentTime each frame and pushes a
  // `transform: translateX(...)` onto the playhead's DOM node. Uses transform
  // instead of `left` so the browser composites it without layout — even
  // smoother on weaker machines. While scrubbing, the playhead follows the
  // pointer's last known position instead of waiting for the video to seek.
  useEffect(() => {
    let rafId = 0
    const tick = (): void => {
      const playhead = playheadRef.current
      const scrub = scrubRef.current
      if (playhead && scrub && durationSec > 0) {
        const rect = scrub.getBoundingClientRect()
        let pct: number
        if (isScrubbingRef.current) {
          pct = (lastPointerXRef.current - rect.left) / rect.width
        } else {
          const video = videoRef.current
          pct = video ? video.currentTime / durationSec : 0
        }
        const clamped = Math.max(0, Math.min(1, pct))
        // translate3d for GPU compositing
        playhead.style.transform = `translate3d(${clamped * rect.width}px, 0, 0)`
      }
      rafId = requestAnimationFrame(tick)
    }
    rafId = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(rafId)
  }, [durationSec, videoRef])

  const seekFromClientX = (clientX: number): void => {
    if (!onSeek || !scrubRef.current || durationSec <= 0) return
    const rect = scrubRef.current.getBoundingClientRect()
    const ratio = (clientX - rect.left) / rect.width
    onSeek(Math.max(0, Math.min(durationSec, ratio * durationSec)))
  }

  const onPointerDown = (event: React.PointerEvent<HTMLDivElement>): void => {
    event.preventDefault()
    event.currentTarget.setPointerCapture(event.pointerId)
    isScrubbingRef.current = true
    lastPointerXRef.current = event.clientX
    setScrubbingCursor(true)
    seekFromClientX(event.clientX)
  }

  const onPointerMove = (event: React.PointerEvent<HTMLDivElement>): void => {
    if (!isScrubbingRef.current) return
    lastPointerXRef.current = event.clientX
    seekFromClientX(event.clientX)
  }

  const stopScrubbing = (event: React.PointerEvent<HTMLDivElement>): void => {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId)
    }
    isScrubbingRef.current = false
    setScrubbingCursor(false)
  }

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
            {/* Ruler — line and label are separate so the rightmost label
                can sit flush-LEFT of its tick line via translateX(-100%)
                instead of overflowing the container. */}
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
              lanes (z-10) so action blocks (pointer-events-none) never steal
              gestures. */}
          <div
            ref={scrubRef}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={stopScrubbing}
            onPointerCancel={stopScrubbing}
            className={`absolute inset-0 z-10 ${scrubbingCursor ? 'cursor-grabbing' : 'cursor-pointer'}`}
            style={{ touchAction: 'none' }}
          />

          {/* Playhead — pointer-events-none so the scrub overlay below still
              receives gestures. Position is driven by the rAF loop above via
              direct DOM mutation (transform), bypassing React renders. */}
          <div
            ref={playheadRef}
            className="pointer-events-none absolute inset-y-0 left-0 z-20 w-px bg-red-400"
            style={{ willChange: 'transform' }}
          />
        </div>
      </div>
    </div>
  )
}
