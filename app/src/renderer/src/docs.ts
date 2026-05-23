/**
 * Documentation export (Step 53).
 *
 * Renders a timeline (optionally clipped to a time window) into
 * human-readable Markdown. Useful for storyboard handoff, compliance
 * records, or sharing the beat-by-beat plan with a collaborator who
 * doesn't have Veraframe open.
 *
 * Pure string formatting — no IPC, no file system. The main process
 * wraps this with a save dialog (see `docs` IPC handler).
 */

import type { Timeline, TimelineAction, TimelineShot } from './timeline-types'

export interface DocExportOptions {
  /** Project label included in the header. */
  projectName?: string
  /** Restrict to actions whose time interval falls inside the window.
   *  Shots that contain at least one in-window action are emitted with
   *  their full metadata, but only the in-window actions are listed.
   *  Pass null/undefined to export the whole timeline. */
  range?: { start: number; end: number } | null
  /** ISO timestamp for the "Exported" header line. Defaults to now()
   *  at call time. Pinned in tests for deterministic output. */
  now?: Date
}

/**
 * Whether an action's time interval overlaps the window. Boundary-
 * touching counts as outside so the user can repeatedly export
 * adjacent ranges without seeing the same beat twice.
 */
function actionInRange(
  a: TimelineAction,
  range: { start: number; end: number } | null | undefined
): boolean {
  if (!range) return true
  return a.end > range.start && a.start < range.end
}

function fmtTime(t: number): string {
  return `${t.toFixed(1)}s`
}

/** Sort action keys so the per-action lines have stable ordering. */
function actionDetailKeys(a: TimelineAction): string[] {
  const skip = new Set(['id', 'type', 'character', 'start', 'end'])
  return Object.keys(a)
    .filter((k) => !skip.has(k))
    .sort()
}

function renderAction(a: TimelineAction): string {
  const head = `**${a.type}**${a.character ? ` (${a.character})` : ''} · ${fmtTime(a.start)}–${fmtTime(a.end)}`
  const details = actionDetailKeys(a)
    .map((k) => {
      const v = a[k]
      if (v === undefined || v === null || v === '') return null
      if (typeof v === 'object') return `${k}: \`${JSON.stringify(v)}\``
      return `${k}: ${typeof v === 'string' ? `\`${v}\`` : v}`
    })
    .filter((s): s is string => s !== null)
  return details.length > 0 ? `- ${head} — ${details.join(', ')}` : `- ${head}`
}

function renderShot(
  shot: TimelineShot,
  index: number,
  range: { start: number; end: number } | null | undefined
): string | null {
  const visible = shot.actions.filter((a) => actionInRange(a, range))
  if (visible.length === 0) return null
  const header = `## Shot ${index + 1} — \`${shot.id}\` · ${fmtTime(shot.start)}–${fmtTime(shot.end)} · camera: \`${shot.camera}\``
  const lines: string[] = [header, '', '### Actions']
  for (const a of visible.sort((x, y) => x.start - y.start)) {
    lines.push(renderAction(a))
  }
  return lines.join('\n')
}

/**
 * Build the markdown doc. The output is deterministic given a fixed
 * `now` so tests can pin it; in production the IPC handler passes
 * `new Date()`.
 */
export function formatTimelineMarkdown(
  timeline: Timeline,
  options: DocExportOptions = {}
): string {
  const { projectName, range, now = new Date() } = options
  const shots = timeline.shots ?? []
  const characters = timeline.characters ?? []
  const allActions = shots.flatMap((s) => s.actions)
  const visibleActions = allActions.filter((a) => actionInRange(a, range))

  const rangeLabel = range
    ? `${fmtTime(range.start)}–${fmtTime(range.end)}`
    : `${fmtTime(Math.min(...shots.map((s) => s.start), 0))}–${fmtTime(
        Math.max(0, ...shots.map((s) => s.end))
      )}`

  const visibleShots = shots
    .map((s, i) => renderShot(s, i, range))
    .filter((s): s is string => s !== null)

  const header = [
    `# Veraframe documentation${projectName ? ` — ${projectName}` : ''}`,
    `Range: ${rangeLabel} · ${visibleShots.length} shot${visibleShots.length === 1 ? '' : 's'} · ${visibleActions.length} action${visibleActions.length === 1 ? '' : 's'}`,
    `Exported: ${now.toISOString()}`,
    '',
    '## Scene',
    `Active scene: \`${timeline.scene}\``,
    '',
    '## Characters'
  ]
  if (characters.length === 0) {
    header.push('(none)')
  } else {
    for (const c of characters) {
      header.push(`- \`${c.id}\` — preset \`${c.preset}\`, spawn \`${c.spawn}\``)
    }
  }
  header.push('')

  if (visibleShots.length === 0) {
    header.push('## Shots', '', '(no actions in this range)')
    return header.join('\n')
  }
  return [...header, ...visibleShots.flatMap((s) => [s, ''])].join('\n').replace(/\n+$/, '\n')
}
