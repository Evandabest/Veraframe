import { describe, it, expect } from 'vitest'

import { compileScriptToPrompt, parseScript } from './script'

describe('parseScript', () => {
  it('parses a single line', () => {
    const out = parseScript('@0 alice walks to the door')
    expect(out.errors).toEqual([])
    expect(out.segments).toHaveLength(1)
    expect(out.segments[0]).toMatchObject({
      start: 0,
      end: null,
      prompt: 'alice walks to the door',
      line: 1
    })
  })

  it('parses multiple lines and backfills missing ends', () => {
    const raw = ['@0 alice walks to the door', '@4 alice waves', '@6-10 they argue'].join('\n')
    const out = parseScript(raw)
    expect(out.errors).toEqual([])
    expect(out.segments).toHaveLength(3)
    expect(out.segments[0].end).toBe(4) // backfilled
    expect(out.segments[1].end).toBe(6) // backfilled
    expect(out.segments[2]).toMatchObject({ start: 6, end: 10 })
  })

  it('accepts decimal timestamps', () => {
    const out = parseScript('@0.5 frown\n@1.5 smile')
    expect(out.errors).toEqual([])
    expect(out.segments[0].start).toBe(0.5)
    expect(out.segments[1].start).toBe(1.5)
  })

  it('accepts explicit ranges @<start>-<end>', () => {
    const out = parseScript('@2-5 sit down')
    expect(out.segments[0]).toMatchObject({ start: 2, end: 5 })
  })

  it('ignores blank lines and # comments', () => {
    const raw = ['# scene 1', '', '@0 alice walks', '# next', '@4 wave'].join('\n')
    const out = parseScript(raw)
    expect(out.errors).toEqual([])
    expect(out.segments).toHaveLength(2)
  })

  it('reports a line that does not start with @', () => {
    const out = parseScript('alice walks')
    expect(out.errors).toHaveLength(1)
    expect(out.errors[0].line).toBe(1)
    expect(out.errors[0].message).toMatch(/must start with @/)
  })

  it('reports empty prompts', () => {
    const out = parseScript('@5   ')
    expect(out.errors).toHaveLength(1)
    expect(out.errors[0].message).toMatch(/empty prompt/)
  })

  it('reports end <= start', () => {
    const out = parseScript('@5-5 nope')
    expect(out.errors).toHaveLength(1)
    expect(out.errors[0].message).toMatch(/must be greater than start/)
  })

  it('reports out-of-order segments', () => {
    const out = parseScript('@5 first\n@2 backwards')
    const orderError = out.errors.find((e) => e.message.includes('previous segment starts'))
    expect(orderError).toBeDefined()
  })

  it('reports overlapping segments', () => {
    const out = parseScript('@0-5 first\n@3 second')
    const overlap = out.errors.find((e) => e.message.includes('overlaps the previous'))
    expect(overlap).toBeDefined()
  })

  it('handles tabs / extra spaces in the prefix', () => {
    const out = parseScript('@ 4   wave')
    expect(out.errors).toEqual([])
    expect(out.segments[0]).toMatchObject({ start: 4, prompt: 'wave' })
  })
})

describe('compileScriptToPrompt', () => {
  it('returns empty string for no segments', () => {
    expect(compileScriptToPrompt([])).toBe('')
  })

  it('emits a numbered list with explicit time windows', () => {
    const { segments } = parseScript('@0 walk\n@4 wave')
    const out = compileScriptToPrompt(segments)
    expect(out).toContain('1. 0s–4s: walk')
    expect(out).toContain('2. 4s–end of video: wave')
  })

  it('preserves explicit end for the final segment when provided', () => {
    const { segments } = parseScript('@0-3 walk\n@3-7 wave')
    const out = compileScriptToPrompt(segments)
    expect(out).toContain('1. 0s–3s: walk')
    expect(out).toContain('2. 3s–7s: wave')
  })
})
