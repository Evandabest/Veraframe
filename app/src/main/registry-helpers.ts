import type { AssetRegistry } from './assets'

export interface RegistrySceneSummaryDTO {
  id: string
  displayName: string
  spawnPoints: string[]
  cameraPresets: string[]
  lightingPresets: string[]
  userProvided: boolean
}

export interface RegistryCharacterSummaryDTO {
  id: string
  displayName: string
  userProvided: boolean
  description: string
  defaultEmotion: string
  voice: string
}

export interface RegistrySummaryDTO {
  scenes: RegistrySceneSummaryDTO[]
  characters: RegistryCharacterSummaryDTO[]
}

/**
 * Project an in-memory AssetRegistry into the shape the renderer expects.
 * A registry entry counts as "user-provided" when its source path lives
 * underneath the user assets directory (uploaded via the GUI), not the
 * repo-bundled `assets/` directory.
 */
export function summarizeRegistry(reg: AssetRegistry | null): RegistrySummaryDTO {
  if (!reg) return { scenes: [], characters: [] }
  const userDir = reg.userAssetsDir
  return {
    scenes: Object.values(reg.scenes).map((s) => ({
      id: s.id,
      displayName: s.displayName,
      spawnPoints: s.spawnPoints,
      cameraPresets: s.cameraPresets,
      lightingPresets: s.lightingPresets,
      userProvided: Boolean(userDir && s.blendPath.startsWith(userDir))
    })),
    characters: Object.values(reg.characters).map((c) => ({
      id: c.id,
      displayName: c.displayName,
      userProvided: Boolean(userDir && c.meshPath.startsWith(userDir)),
      description: c.description,
      defaultEmotion: c.defaultEmotion,
      voice: c.voice
    }))
  }
}
