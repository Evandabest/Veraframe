import { describe, it, expect } from 'vitest'

import {
  captureTake,
  defaultTakeName,
  deleteTake,
  findTake,
  newTakeId,
  renameTake,
  type Take
} from './takes'

const sampleInput = () => ({
  timeline: { project: 'demo', scene: 'lab', shots: [] },
  renderId: 'render_abc',
  videoUrl: 'veraframe-render://render_abc/video.mp4',
  durationSec: 12.5,
  prompt: 'alice walks to the door'
})

describe('defaultTakeName', () => {
  it('starts at "Take 1" for an empty list', () => {
    expect(defaultTakeName([])).toBe('Take 1')
  })

  it('uses N+1 when the list has N takes', () => {
    const takes: Take[] = [
      { ...captureTake([], sampleInput()), name: 'Take 1' },
      { ...captureTake([], sampleInput()), name: 'Take 2' }
    ]
    expect(defaultTakeName(takes)).toBe('Take 3')
  })

  it('skips names already in use even when the list was renamed', () => {
    const takes: Take[] = [
      { ...captureTake([], sampleInput()), name: 'Take 3' }
    ]
    // Length is 1, so the loop starts at "Take 2". That name is free.
    expect(defaultTakeName(takes)).toBe('Take 2')
  })

  it('keeps incrementing past collisions', () => {
    const takes: Take[] = [
      { ...captureTake([], sampleInput()), name: 'Take 1' },
      { ...captureTake([], sampleInput()), name: 'Take 2' },
      { ...captureTake([], sampleInput()), name: 'Take 3' }
    ]
    expect(defaultTakeName(takes)).toBe('Take 4')
  })
})

describe('newTakeId', () => {
  it('encodes the timestamp', () => {
    const id = newTakeId(new Date('2026-05-22T12:00:00Z'))
    expect(id).toMatch(/^take_[a-z0-9_]+$/)
  })

  it('produces different ids for different times', () => {
    const a = newTakeId(new Date('2026-05-22T12:00:00Z'))
    const b = newTakeId(new Date('2026-05-22T12:00:01Z'))
    expect(a).not.toBe(b)
  })
})

describe('captureTake', () => {
  it('stamps id, name, savedAt and carries the input fields', () => {
    const t = captureTake([], sampleInput(), new Date('2026-05-22T12:00:00Z'))
    expect(t.id).toMatch(/^take_/)
    expect(t.name).toBe('Take 1')
    expect(t.savedAt).toBe('2026-05-22T12:00:00.000Z')
    expect(t.renderId).toBe('render_abc')
    expect(t.durationSec).toBe(12.5)
    expect(t.prompt).toBe('alice walks to the door')
  })

  it('does not collide names with existing takes', () => {
    const first = captureTake([], sampleInput())
    const second = captureTake([first], sampleInput())
    expect(second.name).toBe('Take 2')
  })
})

describe('renameTake', () => {
  it('updates the matching take', () => {
    const a = captureTake([], sampleInput())
    const out = renameTake([a], a.id, 'Hero Take')
    expect(out[0].name).toBe('Hero Take')
  })

  it('trims whitespace', () => {
    const a = captureTake([], sampleInput())
    const out = renameTake([a], a.id, '   keep me   ')
    expect(out[0].name).toBe('keep me')
  })

  it('ignores empty / whitespace-only names', () => {
    const a = captureTake([], sampleInput())
    const out = renameTake([a], a.id, '   ')
    expect(out[0].name).toBe(a.name)
  })

  it('leaves other takes untouched', () => {
    const a = captureTake([], sampleInput())
    const b = captureTake([a], sampleInput())
    const out = renameTake([a, b], a.id, 'changed')
    expect(out[1].name).toBe(b.name)
  })
})

describe('deleteTake', () => {
  it('removes the matching take', () => {
    const a = captureTake([], sampleInput())
    const b = captureTake([a], sampleInput())
    const out = deleteTake([a, b], a.id)
    expect(out).toHaveLength(1)
    expect(out[0].id).toBe(b.id)
  })

  it('returns the same length when id is unknown', () => {
    const a = captureTake([], sampleInput())
    expect(deleteTake([a], 'nope')).toHaveLength(1)
  })
})

describe('findTake', () => {
  it('returns the matching take', () => {
    const a = captureTake([], sampleInput())
    expect(findTake([a], a.id)).toEqual(a)
  })

  it('returns null when id is unknown', () => {
    expect(findTake([], 'nope')).toBeNull()
  })
})
