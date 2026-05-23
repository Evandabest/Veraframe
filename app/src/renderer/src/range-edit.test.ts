import { describe, it, expect } from 'vitest'

import { actionsInsideWindow, findContainingShotIndex, mergeRangeEdit } from './range-edit'
import type { Timeline, TimelineAction } from './timeline-types'

const act = (
  id: string,
  start: number,
  end: number,
  extra: Partial<TimelineAction> = {}
): TimelineAction => ({
  id,
  type: 'idle',
  character: 'alice',
  start,
  end,
  ...extra
})

const tl = (shotsActions: TimelineAction[][]): Timeline => ({
  scene: 'lab',
  characters: [{ id: 'alice', preset: 'student_v1', spawn: 'door' }],
  shots: shotsActions.map((actions, i) => ({
    id: `s${i + 1}`,
    start: i === 0 ? 0 : shotsActions.slice(0, i).flat().reduce((m, a) => Math.max(m, a.end), 0),
    end: shotsActions.slice(0, i + 1).flat().reduce((m, a) => Math.max(m, a.end), 0),
    camera: 'wide',
    actions
  }))
})

describe('actionsInsideWindow', () => {
  it('returns only actions fully inside [start, end]', () => {
    const actions = [act('a', 0, 2), act('b', 3, 5), act('c', 4, 7), act('d', 8, 10)]
    const out = actionsInsideWindow(actions, { start: 3, end: 6 })
    expect(out.map((a) => a.id)).toEqual(['b'])
  })

  it('excludes actions that straddle either boundary', () => {
    const actions = [act('left_overlap', 2, 4), act('inside', 4, 5), act('right_overlap', 5, 7)]
    const out = actionsInsideWindow(actions, { start: 3, end: 6 })
    expect(out.map((a) => a.id)).toEqual(['inside'])
  })

  it('includes actions whose edges touch the boundaries exactly', () => {
    const actions = [act('flush_start', 3, 4), act('flush_end', 5, 6)]
    const out = actionsInsideWindow(actions, { start: 3, end: 6 })
    expect(out.map((a) => a.id)).toEqual(['flush_start', 'flush_end'])
  })
})

describe('findContainingShotIndex', () => {
  it('returns the index of the shot fully containing the window', () => {
    const t = tl([[act('a', 0, 5)], [act('b', 5, 10)]])
    expect(findContainingShotIndex(t, { start: 6, end: 9 })).toBe(1)
  })

  it('returns -1 when the window crosses a shot boundary', () => {
    const t = tl([[act('a', 0, 5)], [act('b', 5, 10)]])
    expect(findContainingShotIndex(t, { start: 4, end: 7 })).toBe(-1)
  })

  it('returns -1 when the window is outside any shot', () => {
    const t = tl([[act('a', 0, 5)]])
    expect(findContainingShotIndex(t, { start: 10, end: 12 })).toBe(-1)
  })
})

describe('mergeRangeEdit', () => {
  it('replaces the actions strictly inside the window', () => {
    const t = tl([[act('a', 0, 2), act('b', 3, 5), act('c', 8, 10)]])
    const replacement = [
      act('x', 3, 4, { type: 'wave' }),
      act('y', 4, 5, { type: 'nod' })
    ]
    const out = mergeRangeEdit(t, { start: 3, end: 5 }, replacement)
    const ids = out.timeline.shots[0].actions.map((a) => a.id)
    expect(ids).toEqual(['a', 'x', 'y', 'c'])
    expect(out.removed).toEqual(['b'])
    expect(out.inserted).toEqual(['x', 'y'])
  })

  it('preserves actions that straddle the boundary', () => {
    const t = tl([[act('crosses_start', 2, 4), act('crosses_end', 5, 7)]])
    const replacement = [act('x', 3, 6, { type: 'idle' })]
    const out = mergeRangeEdit(t, { start: 3, end: 6 }, replacement)
    expect(out.removed).toEqual([])
    expect(out.inserted).toEqual(['x'])
    expect(out.timeline.shots[0].actions.map((a) => a.id)).toEqual([
      'crosses_start',
      'x',
      'crosses_end'
    ])
  })

  it('sorts the merged actions by start time', () => {
    const t = tl([[act('first', 0, 1), act('last', 5, 6)]])
    const replacement = [act('mid_b', 3, 4), act('mid_a', 2, 3)]
    const out = mergeRangeEdit(t, { start: 1, end: 5 }, replacement)
    expect(out.timeline.shots[0].actions.map((a) => a.id)).toEqual(['first', 'mid_a', 'mid_b', 'last'])
  })

  it('only mutates the shot containing the window', () => {
    const t = tl([[act('s1a', 0, 4)], [act('s2a', 4, 6), act('s2b', 7, 9)]])
    const replacement = [act('x', 4, 5)]
    const out = mergeRangeEdit(t, { start: 4, end: 6 }, replacement)
    // s1 untouched.
    expect(out.timeline.shots[0].actions.map((a) => a.id)).toEqual(['s1a'])
    // s2 replaces s2a with x.
    expect(out.timeline.shots[1].actions.map((a) => a.id)).toEqual(['x', 's2b'])
  })

  it('throws when the window does not fit in any shot', () => {
    const t = tl([[act('a', 0, 5)], [act('b', 5, 10)]])
    expect(() => mergeRangeEdit(t, { start: 3, end: 7 }, [])).toThrow(/does not fit/)
  })

  it('throws on inverted windows', () => {
    const t = tl([[act('a', 0, 5)]])
    expect(() => mergeRangeEdit(t, { start: 5, end: 3 }, [])).toThrow(/must be >/)
  })

  it('accepts an empty replacement list (pure deletion)', () => {
    const t = tl([[act('keep', 0, 2), act('drop', 3, 5), act('keep2', 6, 8)]])
    const out = mergeRangeEdit(t, { start: 3, end: 5 }, [])
    expect(out.timeline.shots[0].actions.map((a) => a.id)).toEqual(['keep', 'keep2'])
    expect(out.removed).toEqual(['drop'])
  })
})
