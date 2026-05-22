/**
 * Read-only timeline viewer.
 *
 * Renders one horizontal lane per character + one for scene-level actions
 * (camera_*, set_lighting). Action blocks are positioned by start/end times
 * scaled to lane width. A vertical playhead line is driven by the host's
 * `currentTimeSec` prop (App.tsx wires this from the <video> element's
 * timeupdate event). Clicking the content column seeks the video.
 */

import { Fragment } from 'react'

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

  const handleContentClick = (event: React.MouseEvent<HTMLDivElement>): void => {
    if (!onSeek) return
    const rect = event.currentTarget.getBoundingClientRect()
    const ratio = (event.clientX - rect.left) / rect.width
    onSeek(Math.max(0, Math.min(durationSec, ratio * durationSec)))
  }

  return (
    <div className="flex flex-col gap-2 rounded-lg border border-neutral-800 bg-neutral-900 p-3">
      <div className="flex items-baseline justify-between">
        <h2 className="text-sm font-semibold text-neutral-200">Timeline</h2>
        <span className="text-xs text-neutral-500">
          scene: <span className="text-neutral-300">{tl.scene}</span> · {actions.length} action
          {actions.length === 1 ? '' : 's'} · {durationSec.toFixed(1)}s
        </span>
      </div>

      <div className="grid grid-cols-[6rem_1fr] gap-x-2">
        {/* Ruler row */}
        <div />
        <div className="relative h-5 border-b border-neutral-800">
          {ticks.map((t) => (
            <div
              key={t}
              className="absolute top-0 h-full border-l border-neutral-800 pl-1 text-[10px] text-neutral-500"
              style={{ left: `${(t / durationSec) * 100}%` }}
            >
              {t}s
            </div>
          ))}
        </div>

        {/* Lanes */}
        {lanes.length === 0 && (
          <>
            <div />
            <p className="text-sm text-neutral-500">No actions in this timeline.</p>
          </>
        )}
        {lanes.map((lane) => (
          <Fragment key={lane.id}>
            <div className="flex h-8 items-center text-xs text-neutral-400">
              {lane.label}
            </div>
            <div
              className="relative h-8 cursor-pointer rounded bg-neutral-950/60"
              onClick={handleContentClick}
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
              {/* Per-lane playhead segment — combined with the others it forms
                  a vertical red line spanning all lanes. */}
              {durationSec > 0 && (
                <div
                  className="pointer-events-none absolute top-0 bottom-0 w-px bg-red-400"
                  style={{ left: `${(currentTimeSec / durationSec) * 100}%` }}
                />
              )}
            </div>
          </Fragment>
        ))}
      </div>
    </div>
  )
}
