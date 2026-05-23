import { describe, it, expect } from 'vitest'

import {
  buildProjectFile,
  parseProjectFile,
  serializeProjectFile,
  type ProjectFilePayload
} from './project-file'

const samplePayload = (): ProjectFilePayload => ({
  selectedScene: 'dark_lab',
  selectedCharacters: ['student'],
  prompt: 'walk to the door',
  mode: 'mock',
  provider: 'openai',
  model: 'gpt-4',
  timeline: null
})

describe('buildProjectFile', () => {
  it('stamps version=1 and an ISO timestamp', () => {
    const file = buildProjectFile(samplePayload(), new Date('2026-05-22T12:34:56Z'))
    expect(file.version).toBe(1)
    expect(file.savedAt).toBe('2026-05-22T12:34:56.000Z')
  })

  it('preserves payload fields verbatim', () => {
    const payload = samplePayload()
    const file = buildProjectFile(payload)
    expect(file.selectedScene).toBe('dark_lab')
    expect(file.selectedCharacters).toEqual(['student'])
    expect(file.prompt).toBe('walk to the door')
    expect(file.mode).toBe('mock')
  })

  it('persists projectStyle when supplied', () => {
    const file = buildProjectFile({
      ...samplePayload(),
      projectStyle: { lighting: 'night' }
    })
    expect(file.projectStyle).toEqual({ lighting: 'night' })
  })

  it('leaves projectStyle undefined when omitted (back-compat)', () => {
    const file = buildProjectFile(samplePayload())
    expect(file.projectStyle).toBeUndefined()
  })
})

describe('serializeProjectFile', () => {
  it('produces pretty-printed JSON', () => {
    const raw = serializeProjectFile(samplePayload())
    expect(raw).toContain('\n  "version": 1')
  })

  it('round-trips through parseProjectFile', () => {
    const raw = serializeProjectFile({
      ...samplePayload(),
      projectStyle: { lighting: 'day' }
    })
    const out = parseProjectFile(raw)
    if (!out.ok) throw new Error(out.error)
    expect(out.project.projectStyle).toEqual({ lighting: 'day' })
    expect(out.project.prompt).toBe('walk to the door')
  })
})

describe('parseProjectFile', () => {
  it('rejects non-JSON', () => {
    const out = parseProjectFile('not json')
    expect(out.ok).toBe(false)
  })

  it('rejects non-object JSON', () => {
    const out = parseProjectFile('null')
    if (out.ok) throw new Error('expected failure')
    expect(out.error).toMatch(/not a JSON object/)
  })

  it('rejects unsupported versions', () => {
    const raw = JSON.stringify({ ...samplePayload(), version: 99, savedAt: 'x' })
    const out = parseProjectFile(raw)
    if (out.ok) throw new Error('expected failure')
    expect(out.error).toMatch(/unsupported project version/)
  })

  it('accepts older files missing projectStyle', () => {
    const legacy = {
      version: 1,
      savedAt: '2026-01-01T00:00:00.000Z',
      ...samplePayload()
    }
    const out = parseProjectFile(JSON.stringify(legacy))
    if (!out.ok) throw new Error(out.error)
    expect(out.project.projectStyle).toBeUndefined()
    expect(out.project.selectedScene).toBe('dark_lab')
  })

  it('round-trips a takes array', () => {
    const raw = serializeProjectFile({
      ...samplePayload(),
      takes: [
        {
          id: 'take_1',
          name: 'Take 1',
          savedAt: '2026-05-22T12:00:00.000Z',
          timeline: { project: 'demo', scene: 'lab', shots: [] },
          renderId: 'render_abc',
          videoUrl: 'veraframe-render://render_abc/video.mp4',
          durationSec: 12.5,
          prompt: 'walk'
        }
      ]
    })
    const out = parseProjectFile(raw)
    if (!out.ok) throw new Error(out.error)
    expect(out.project.takes).toHaveLength(1)
    expect(out.project.takes?.[0].name).toBe('Take 1')
    expect(out.project.takes?.[0].renderId).toBe('render_abc')
  })

  it('accepts older files missing takes', () => {
    const legacy = {
      version: 1,
      savedAt: '2026-01-01T00:00:00.000Z',
      ...samplePayload()
    }
    const out = parseProjectFile(JSON.stringify(legacy))
    if (!out.ok) throw new Error(out.error)
    expect(out.project.takes).toBeUndefined()
  })
})
