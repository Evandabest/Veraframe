import { describe, it, expect } from 'vitest'

import {
  buildCharacterManifest,
  buildSceneManifest,
  detectCharacterFiles,
  deriveSceneExtension,
  isValidAssetId,
  pickSceneFile
} from './asset-helpers'

describe('isValidAssetId', () => {
  it.each([
    ['alice', true],
    ['student_v2', true],
    ['Robot42', true],
    ['', false],
    ['has space', false],
    ['has-dash', false],
    ['has.dot', false],
    ['emoji😀', false]
  ])('id %j → valid=%s', (id, valid) => {
    expect(isValidAssetId(id)).toBe(valid)
  })
})

describe('detectCharacterFiles', () => {
  it('matches canonical names exactly', () => {
    const out = detectCharacterFiles(['character.fbx', 'idle.fbx', 'walk_in_place.fbx'])
    expect(out).toEqual({
      mesh: 'character.fbx',
      idle: 'idle.fbx',
      walk: 'walk_in_place.fbx'
    })
  })

  it('falls back to walk.fbx alias for the walk slot', () => {
    const out = detectCharacterFiles(['character.fbx', 'idle.fbx', 'walk.fbx'])
    expect(out.walk).toBe('walk.fbx')
  })

  it('picks a "first non-idle/walk" fbx as the mesh', () => {
    const out = detectCharacterFiles(['hero.fbx', 'idle.fbx', 'walk_in_place.fbx'])
    expect(out.mesh).toBe('hero.fbx')
  })

  it('returns nulls for slots with no candidates', () => {
    const out = detectCharacterFiles(['readme.txt'])
    expect(out).toEqual({ mesh: null, idle: null, walk: null })
  })

  it('ignores non-fbx files entirely', () => {
    const out = detectCharacterFiles(['character.fbx', 'thumbnail.png', 'idle.fbx', 'walk.fbx'])
    expect(out.mesh).toBe('character.fbx')
    expect(out.idle).toBe('idle.fbx')
  })

  it('does not pick a file containing "idle" or "walk" as the mesh', () => {
    // Without an explicit mesh.fbx/character.fbx, the picker should still
    // refuse the idle/walk fbx for the mesh slot.
    const out = detectCharacterFiles(['idle.fbx', 'walk.fbx'])
    expect(out.mesh).toBeNull()
  })
})

describe('pickSceneFile', () => {
  it('prefers scene.blend over other .blend files', () => {
    expect(pickSceneFile(['lighting.blend', 'scene.blend'])).toBe('scene.blend')
  })

  it('prefers scene.fbx over other .fbx files', () => {
    expect(pickSceneFile(['extras.fbx', 'scene.fbx'])).toBe('scene.fbx')
  })

  it('falls back to the first candidate when no canonical scene.* exists', () => {
    expect(pickSceneFile(['stage_v3.blend', 'extras.blend'])).toBe('stage_v3.blend')
  })

  it('returns null when no .blend/.fbx is present', () => {
    expect(pickSceneFile(['readme.md', 'thumbnail.png'])).toBeNull()
  })

  it('accepts mixed-case extensions', () => {
    expect(pickSceneFile(['Scene.BLEND'])).toBe('Scene.BLEND')
  })
})

describe('deriveSceneExtension', () => {
  it('returns "fbx" for .fbx sources', () => {
    expect(deriveSceneExtension('/tmp/scene.fbx')).toBe('fbx')
    expect(deriveSceneExtension('/tmp/SCENE.FBX')).toBe('fbx')
  })

  it('returns "blend" for everything else', () => {
    expect(deriveSceneExtension('/tmp/scene.blend')).toBe('blend')
    expect(deriveSceneExtension('/tmp/something.unknown')).toBe('blend')
    expect(deriveSceneExtension('/tmp/noext')).toBe('blend')
  })
})

describe('buildSceneManifest', () => {
  it('serializes required fields', () => {
    const m = buildSceneManifest({
      id: 'stage',
      displayName: 'Stage',
      blendFile: 'scene.blend',
      spawnPoints: ['door'],
      cameraPresets: ['wide']
    })
    expect(m).toEqual({
      id: 'stage',
      display_name: 'Stage',
      description: '',
      blend_file: 'scene.blend',
      spawn_points: ['door'],
      camera_presets: ['wide'],
      lighting_presets: ['default']
    })
  })

  it('uses provided lightingPresets verbatim', () => {
    const m = buildSceneManifest({
      id: 'stage',
      displayName: 'Stage',
      blendFile: 'scene.blend',
      spawnPoints: [],
      cameraPresets: [],
      lightingPresets: ['day', 'night']
    })
    expect(m.lighting_presets).toEqual(['day', 'night'])
  })
})

describe('buildCharacterManifest', () => {
  it('always uses canonical relative file names', () => {
    const m = buildCharacterManifest({ id: 'alice', displayName: 'Alice' })
    expect(m.mesh_file).toBe('character.fbx')
    expect(m.animations).toEqual({
      idle: 'idle.fbx',
      walk_in_place: 'walk_in_place.fbx'
    })
    expect(m.rig_type).toBe('mixamo')
  })

  it('passes through the description', () => {
    const m = buildCharacterManifest({
      id: 'alice',
      displayName: 'Alice',
      description: 'lab student'
    })
    expect(m.description).toBe('lab student')
  })
})
