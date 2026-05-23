import { describe, it, expect } from 'vitest'

import type { AssetRegistry } from './assets'
import { summarizeRegistry } from './registry-helpers'

const fakeRegistry = (userDir?: string): AssetRegistry => ({
  assetsDir: '/repo/assets',
  userAssetsDir: userDir,
  scenes: {
    repo_stage: {
      id: 'repo_stage',
      displayName: 'Repo Stage',
      blendPath: '/repo/assets/scenes/repo_stage/scene.blend',
      spawnPoints: ['door'],
      cameraPresets: ['wide'],
      lightingPresets: ['day']
    },
    user_stage: {
      id: 'user_stage',
      displayName: 'User Stage',
      blendPath: '/Users/x/userdata/scenes/user_stage/scene.blend',
      spawnPoints: [],
      cameraPresets: [],
      lightingPresets: []
    }
  },
  characters: {
    alice: {
      id: 'alice',
      displayName: 'Alice',
      meshPath: '/repo/assets/characters/alice/mesh.fbx',
      rigType: 'mixamo',
      animations: {}
    },
    bob: {
      id: 'bob',
      displayName: 'Bob',
      meshPath: '/Users/x/userdata/characters/bob/mesh.fbx',
      rigType: 'mixamo',
      animations: {}
    }
  },
  animations: {}
})

describe('summarizeRegistry', () => {
  it('returns empty arrays for null registry', () => {
    expect(summarizeRegistry(null)).toEqual({ scenes: [], characters: [] })
  })

  it('projects scene and character fields the renderer needs', () => {
    const out = summarizeRegistry(fakeRegistry('/Users/x/userdata'))
    const repoScene = out.scenes.find((s) => s.id === 'repo_stage')!
    expect(repoScene.displayName).toBe('Repo Stage')
    expect(repoScene.spawnPoints).toEqual(['door'])
    expect(repoScene.cameraPresets).toEqual(['wide'])
    expect(repoScene.lightingPresets).toEqual(['day'])
  })

  it('marks scenes whose blendPath is under userAssetsDir as userProvided', () => {
    const out = summarizeRegistry(fakeRegistry('/Users/x/userdata'))
    const repoScene = out.scenes.find((s) => s.id === 'repo_stage')!
    const userScene = out.scenes.find((s) => s.id === 'user_stage')!
    expect(repoScene.userProvided).toBe(false)
    expect(userScene.userProvided).toBe(true)
  })

  it('marks characters whose meshPath is under userAssetsDir as userProvided', () => {
    const out = summarizeRegistry(fakeRegistry('/Users/x/userdata'))
    const alice = out.characters.find((c) => c.id === 'alice')!
    const bob = out.characters.find((c) => c.id === 'bob')!
    expect(alice.userProvided).toBe(false)
    expect(bob.userProvided).toBe(true)
  })

  it('treats everything as repo-bundled when userAssetsDir is undefined', () => {
    const out = summarizeRegistry(fakeRegistry(undefined))
    expect(out.scenes.every((s) => !s.userProvided)).toBe(true)
    expect(out.characters.every((c) => !c.userProvided)).toBe(true)
  })

  it('does not leak internal fields like blendPath into the DTO', () => {
    const out = summarizeRegistry(fakeRegistry())
    const scene = out.scenes[0] as unknown as Record<string, unknown>
    expect(scene.blendPath).toBeUndefined()
  })
})
