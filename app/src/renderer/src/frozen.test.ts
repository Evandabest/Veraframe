import { describe, it, expect } from 'vitest'

import { frozenInWindow, isFrozen, toggleFrozen } from './frozen'
import type { TimelineAction } from './timeline-types'

const act = (id: string, start: number, end: number): TimelineAction => ({
  id,
  type: 'idle',
  character: 'alice',
  start,
  end
})

describe('toggleFrozen', () => {
  it('adds when missing', () => {
    expect(toggleFrozen([], 'a1')).toEqual(['a1'])
  })

  it('removes when present', () => {
    expect(toggleFrozen(['a1', 'a2'], 'a1').sort()).toEqual(['a2'])
  })

  it('dedupes input', () => {
    expect(toggleFrozen(['a1', 'a1'], 'a2').sort()).toEqual(['a1', 'a2'])
  })
})

describe('isFrozen', () => {
  it('returns true for ids in the set', () => {
    expect(isFrozen(['a1'], 'a1')).toBe(true)
  })
  it('returns false otherwise', () => {
    expect(isFrozen(['a1'], 'a2')).toBe(false)
    expect(isFrozen([], 'a1')).toBe(false)
  })
})

describe('frozenInWindow', () => {
  const actions = [
    act('a', 0, 2),
    act('b', 3, 5),
    act('c', 4, 7),
    act('d', 8, 10)
  ]

  it('returns frozen actions that fully sit inside the window', () => {
    const out = frozenInWindow(actions, ['b'], { start: 3, end: 5 })
    expect(out.map((a) => a.id)).toEqual(['b'])
  })

  it('flags frozen actions that straddle the window', () => {
    const out = frozenInWindow(actions, ['c'], { start: 3, end: 5 })
    // c spans 4-7; window 3-5 overlaps the front half of c.
    expect(out.map((a) => a.id)).toEqual(['c'])
  })

  it('ignores frozen actions outside the window', () => {
    const out = frozenInWindow(actions, ['a', 'd'], { start: 3, end: 7 })
    expect(out).toEqual([])
  })

  it('ignores non-frozen actions even if they overlap', () => {
    const out = frozenInWindow(actions, [], { start: 3, end: 7 })
    expect(out).toEqual([])
  })

  it('treats edge-touching actions as non-overlapping', () => {
    // Action ends exactly at window.start → not overlapping.
    const out = frozenInWindow([act('flush', 1, 3)], ['flush'], { start: 3, end: 5 })
    expect(out).toEqual([])
  })
})
