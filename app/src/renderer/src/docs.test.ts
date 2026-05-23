import { describe, it, expect } from 'vitest'

import { formatTimelineMarkdown } from './docs'
import type { Timeline, TimelineAction } from './timeline-types'

const NOW = new Date('2026-05-22T12:00:00Z')

const act = (
  id: string,
  type: string,
  start: number,
  end: number,
  extra: Partial<TimelineAction> = {}
): TimelineAction => ({
  id,
  type,
  character: 'alice',
  start,
  end,
  ...extra
})

const sampleTimeline = (): Timeline => ({
  scene: 'classroom',
  characters: [
    { id: 'alice', preset: 'student_v1', spawn: 'door' },
    { id: 'bob', preset: 'robot_placeholder', spawn: 'robot_station' }
  ],
  shots: [
    {
      id: 's1',
      start: 0,
      end: 6,
      camera: 'wide',
      actions: [
        act('a1', 'walk_to', 0, 4, { target: 'center_room' }),
        act('a2', 'talk', 1, 3, { text: 'where is it?' })
      ]
    },
    {
      id: 's2',
      start: 6,
      end: 10,
      camera: 'close_student',
      actions: [act('a3', 'wave', 7, 9, { character: 'alice' })]
    }
  ]
})

describe('formatTimelineMarkdown', () => {
  it('includes header, scene, characters, and shots when no range is set', () => {
    const md = formatTimelineMarkdown(sampleTimeline(), { now: NOW })
    expect(md).toMatch(/^# Veraframe documentation/)
    expect(md).toContain('Active scene: `classroom`')
    expect(md).toContain('- `alice` — preset `student_v1`, spawn `door`')
    expect(md).toContain('Shot 1 — `s1`')
    expect(md).toContain('Shot 2 — `s2`')
    expect(md).toContain('Exported: 2026-05-22T12:00:00.000Z')
  })

  it('renders action detail keys (target, text) as kv pairs', () => {
    const md = formatTimelineMarkdown(sampleTimeline(), { now: NOW })
    expect(md).toContain('**walk_to** (alice) · 0.0s–4.0s — target: `center_room`')
    expect(md).toContain('text: `where is it?`')
  })

  it('clips to a range and drops shots with no in-range action', () => {
    const md = formatTimelineMarkdown(sampleTimeline(), {
      range: { start: 6, end: 10 },
      now: NOW
    })
    expect(md).not.toContain('walk_to')
    expect(md).not.toContain('where is it')
    // We keep the original shot index so users can correlate the doc
    // with their timeline; s2 is still "Shot 2" even when s1 is dropped.
    expect(md).toContain('Shot 2 — `s2`')
    expect(md).toContain('Range: 6.0s–10.0s · 1 shot · 1 action')
  })

  it('includes a shot when any single action overlaps the range', () => {
    const md = formatTimelineMarkdown(sampleTimeline(), {
      range: { start: 2, end: 5 },
      now: NOW
    })
    // walk_to (0-4) and talk (1-3) both overlap 2-5. wave (7-9) does not.
    expect(md).toContain('walk_to')
    expect(md).toContain('talk')
    expect(md).not.toContain('wave')
  })

  it('shows an "no actions" placeholder when the range hits nothing', () => {
    const md = formatTimelineMarkdown(sampleTimeline(), {
      range: { start: 20, end: 30 },
      now: NOW
    })
    expect(md).toContain('(no actions in this range)')
  })

  it('treats boundary-touching actions as outside the window', () => {
    // walk_to is 0-4. Range 4-6 starts exactly where walk_to ends — it
    // should be excluded so the user can chain adjacent exports without
    // double-listing.
    const md = formatTimelineMarkdown(sampleTimeline(), {
      range: { start: 4, end: 6 },
      now: NOW
    })
    expect(md).not.toContain('walk_to')
  })

  it('honors the project name', () => {
    const md = formatTimelineMarkdown(sampleTimeline(), {
      projectName: 'Lab Demo',
      now: NOW
    })
    expect(md.split('\n')[0]).toBe('# Veraframe documentation — Lab Demo')
  })

  it('shows (none) when there are no characters', () => {
    const tl: Timeline = { ...sampleTimeline(), characters: [] }
    const md = formatTimelineMarkdown(tl, { now: NOW })
    expect(md).toContain('## Characters\n(none)')
  })
})
