import { describe, it, expect } from 'vitest'

import { KNOWN_ACTION_TYPES, VERB_FAMILIES, allVerbs, verbByType } from './verbs'

describe('verb catalog', () => {
  it('lists every ActionType from the schema', () => {
    const palette = new Set(allVerbs().map((v) => v.type))
    for (const t of KNOWN_ACTION_TYPES) {
      expect(palette.has(t)).toBe(true)
    }
  })

  it('does not invent verbs the schema does not have', () => {
    const known = new Set(KNOWN_ACTION_TYPES)
    for (const v of allVerbs()) {
      expect(known.has(v.type)).toBe(true)
    }
  })

  it('has no duplicate verb types across families', () => {
    const seen = new Set<string>()
    for (const v of allVerbs()) {
      expect(seen.has(v.type), `duplicate verb: ${v.type}`).toBe(false)
      seen.add(v.type)
    }
  })

  it('marks camera + stage verbs as scene-targeted', () => {
    const cameraFamily = VERB_FAMILIES.find((f) => f.id === 'camera')!
    const stageFamily = VERB_FAMILIES.find((f) => f.id === 'stage')!
    expect(cameraFamily.verbs.every((v) => v.scene)).toBe(true)
    expect(stageFamily.verbs.every((v) => v.scene)).toBe(true)
  })

  it('marks character verbs (gesture, face, locomotion, ...) as non-scene', () => {
    for (const family of VERB_FAMILIES) {
      if (family.id === 'camera' || family.id === 'stage') continue
      expect(family.verbs.every((v) => !v.scene), `family ${family.id}`).toBe(true)
    }
  })

  it('every verb has a non-empty prompt seed', () => {
    for (const v of allVerbs()) {
      expect(v.promptSeed.length, `${v.type} promptSeed`).toBeGreaterThan(0)
    }
  })

  it('verbByType returns the right verb (or undefined)', () => {
    expect(verbByType('nod')?.label).toBe('nod')
    expect(verbByType('not_a_real_action')).toBeUndefined()
  })

  it('families are non-empty and uniquely-id’d', () => {
    const ids = new Set<string>()
    for (const f of VERB_FAMILIES) {
      expect(f.verbs.length, `family ${f.id}`).toBeGreaterThan(0)
      expect(ids.has(f.id), `duplicate family id ${f.id}`).toBe(false)
      ids.add(f.id)
    }
  })
})
