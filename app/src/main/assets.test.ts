import { afterEach, beforeEach, describe, it, expect } from 'vitest'
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'fs'
import { join } from 'path'
import { tmpdir } from 'os'

import { loadAssets } from './assets'

let root: string

beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), 'veraframe-assets-'))
})

afterEach(() => {
  rmSync(root, { recursive: true, force: true })
})

function writeManifest(path: string, body: Record<string, unknown>): void {
  mkdirSync(path.substring(0, path.lastIndexOf('/')), { recursive: true })
  writeFileSync(path, JSON.stringify(body), 'utf8')
}

describe('loadAssets', () => {
  it('returns empty registry when no asset dirs exist', () => {
    const reg = loadAssets(root)
    expect(reg.scenes).toEqual({})
    expect(reg.characters).toEqual({})
    expect(reg.animations).toEqual({})
  })

  it('reads a scene manifest including lighting_presets', () => {
    writeManifest(`${root}/scenes/s1/scene.json`, {
      id: 's1',
      display_name: 'Stage',
      blend_file: 'scene.blend',
      spawn_points: ['door', 'center'],
      camera_presets: ['wide', 'close'],
      lighting_presets: ['day', 'night']
    })
    const reg = loadAssets(root)
    expect(reg.scenes.s1.id).toBe('s1')
    expect(reg.scenes.s1.displayName).toBe('Stage')
    expect(reg.scenes.s1.spawnPoints).toEqual(['door', 'center'])
    expect(reg.scenes.s1.cameraPresets).toEqual(['wide', 'close'])
    expect(reg.scenes.s1.lightingPresets).toEqual(['day', 'night'])
    expect(reg.scenes.s1.blendPath.endsWith('/scenes/s1/scene.blend')).toBe(true)
  })

  it('defaults lighting_presets to [] when missing', () => {
    writeManifest(`${root}/scenes/s1/scene.json`, {
      id: 's1',
      blend_file: 'scene.blend',
      spawn_points: [],
      camera_presets: []
    })
    expect(loadAssets(root).scenes.s1.lightingPresets).toEqual([])
  })

  it('reads character manifest with per-character animations', () => {
    writeManifest(`${root}/characters/c1/character.json`, {
      id: 'c1',
      display_name: 'Alice',
      mesh_file: 'mesh.fbx',
      rig_type: 'mixamo',
      animations: { idle: 'idle.fbx', walk_in_place: 'walk.fbx' }
    })
    const reg = loadAssets(root)
    expect(reg.characters.c1.displayName).toBe('Alice')
    expect(reg.characters.c1.rigType).toBe('mixamo')
    expect(reg.characters.c1.animations.idle.endsWith('/characters/c1/idle.fbx')).toBe(true)
    expect(reg.characters.c1.animations.walk_in_place.endsWith('/characters/c1/walk.fbx')).toBe(
      true
    )
  })

  it('skips directories without a manifest', () => {
    mkdirSync(`${root}/scenes/orphan`, { recursive: true })
    const reg = loadAssets(root)
    expect(reg.scenes).toEqual({})
  })

  it('user assets override repo assets when ids collide', () => {
    writeManifest(`${root}/repo/scenes/s1/scene.json`, {
      id: 's1',
      display_name: 'Repo Stage',
      blend_file: 'scene.blend',
      spawn_points: [],
      camera_presets: []
    })
    writeManifest(`${root}/user/scenes/s1/scene.json`, {
      id: 's1',
      display_name: 'User Stage',
      blend_file: 'scene.blend',
      spawn_points: [],
      camera_presets: []
    })
    const reg = loadAssets(`${root}/repo`, `${root}/user`)
    expect(reg.scenes.s1.displayName).toBe('User Stage')
    expect(reg.scenes.s1.blendPath.startsWith(`${root}/user`)).toBe(true)
  })

  it('records userAssetsDir for downstream provenance checks', () => {
    const reg = loadAssets(`${root}/repo`, `${root}/user`)
    expect(reg.userAssetsDir).toBe(`${root}/user`)
  })

  it('reads an animation manifest', () => {
    writeManifest(`${root}/animations/idle/animation.json`, {
      id: 'idle',
      display_name: 'Idle',
      fbx_file: 'idle.fbx'
    })
    const reg = loadAssets(root)
    expect(reg.animations.idle.fbxPath.endsWith('/animations/idle/idle.fbx')).toBe(true)
  })
})
