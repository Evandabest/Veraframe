import { contextBridge, ipcRenderer } from 'electron'
import { electronAPI } from '@electron-toolkit/preload'

export type LLMProvider = 'openai' | 'anthropic' | 'gemini' | 'ollama'

export interface IncrementalRenderRequest {
  previousRenderId: string
  changedWindow: { start: number; end: number }
  operation: 'splice' | 'append'
}

export interface RenderRequest {
  mode: 'mock' | 'llm' | 'direct'
  prompt?: string
  durationSec?: number
  /** Provider for LLM mode; ignored in mock mode. */
  provider?: LLMProvider
  /** Model name (without `provider/` prefix). LiteLLM joins them. */
  model?: string
  /** Optional Ollama base URL (defaults to http://localhost:11434). */
  ollamaHost?: string
  /** Required when mode='direct'; an already-resolved timeline JSON. */
  timeline?: Record<string, unknown>
  /** When set, render only the changed window and ffmpeg-splice/append into
   *  the prior video. Only valid with mode='direct'. */
  incremental?: IncrementalRenderRequest
  /** Hard-constrain LLM to this scene id. */
  selectedScene?: string
  /** Hard-constrain LLM character pool to these preset ids. */
  selectedCharacters?: string[]
  /** Render quality preset. 'draft' = fast iteration; 'hifi' = full quality. */
  quality?: 'draft' | 'hifi'
}

export interface RegistrySceneSummary {
  id: string
  displayName: string
  spawnPoints: string[]
  cameraPresets: string[]
  userProvided: boolean
}

export interface RegistryCharacterSummary {
  id: string
  displayName: string
  userProvided: boolean
}

export interface RegistrySummary {
  scenes: RegistrySceneSummary[]
  characters: RegistryCharacterSummary[]
}

export interface AddSceneRequest {
  sourcePath: string
  id: string
  displayName: string
  description?: string
  spawnPoints: string[]
  cameraPresets: string[]
  lightingPresets?: string[]
}

export interface AddCharacterRequest {
  sourcePath: string
  idlePath: string
  walkPath: string
  id: string
  displayName: string
  description?: string
}

export interface UpdateCharacterRequest {
  id: string
  meshPath?: string | null
  idlePath?: string | null
  walkPath?: string | null
  displayName?: string | null
  description?: string | null
}

export interface ProjectFile {
  version: 1
  savedAt: string
  selectedScene: string | null
  selectedCharacters: string[]
  prompt: string
  mode: 'mock' | 'llm'
  provider: string
  model: string
  timeline: Record<string, unknown> | null
}

export type SaveProjectResponse =
  | { ok: true; path: string }
  | { ok: false; error: string }

export type OpenProjectResponse =
  | { ok: true; project: ProjectFile; path: string }
  | { ok: false; error: string }

export type PickCharacterFolderResponse =
  | {
      ok: true
      kind: 'character'
      folderPath: string
      mesh: string
      idle: string
      walk: string
      manifest: { id?: string; displayName?: string; description?: string } | null
    }
  | { ok: false; error: string }

export type PickSceneFolderResponse =
  | {
      ok: true
      kind: 'scene'
      folderPath: string
      sceneFile: string
      manifest: {
        id?: string
        displayName?: string
        description?: string
        spawnPoints?: string[]
        cameraPresets?: string[]
        lightingPresets?: string[]
      } | null
    }
  | { ok: false; error: string }

export interface UpdateSceneRequest {
  id: string
  scenePath?: string | null
  displayName?: string | null
  description?: string | null
  spawnPoints?: string[] | null
  cameraPresets?: string[] | null
}

export type AddAssetResponse = { ok: true; id: string } | { ok: false; error: string }
export type PickAssetFileResponse =
  | { ok: true; filePath: string }
  | { ok: false; error: string }

export type RenderResponse =
  | {
      ok: true
      renderId: string
      videoUrl: string
      durationSec: number
      executed: number
      skipped: number
      timeline: Record<string, unknown>
    }
  | { ok: false; error: string }

export type SaveRenderResponse = { ok: true; path: string } | { ok: false; error: string }

export type OllamaModelsResponse =
  | { ok: true; models: string[] }
  | { ok: false; error: string }

export type EnhancePromptResponse =
  | { ok: true; prompt: string }
  | { ok: false; error: string }

export interface EnhancePromptRequest {
  prompt: string
  provider?: LLMProvider
  model?: string
  ollamaHost?: string
}

export interface RenderStatusEvent {
  step: string
  detail?: string
}

export type DaemonState = 'starting' | 'ready' | 'crashed' | 'restarting' | 'stopped'

export interface DaemonStatusEvent {
  state: DaemonState
  detail?: string
}

export interface GenerateActionRequest {
  prompt: string
  scene: string
  character: string
  actionId: string
  start: number
  /** Optional. If omitted, the LLM picks the action's duration. */
  end?: number
  timelineContext: Record<string, unknown>
  provider?: LLMProvider
  model?: string
}

export type GenerateActionResponse =
  | { ok: true; action: Record<string, unknown> }
  | { ok: false; error: string }

/** API surface exposed on `window.veraframe` for the React renderer. */
const veraframe = {
  render: (request: RenderRequest): Promise<RenderResponse> =>
    ipcRenderer.invoke('render', request),
  saveRender: (renderId: string): Promise<SaveRenderResponse> =>
    ipcRenderer.invoke('saveRender', renderId),
  listOllamaModels: (host: string): Promise<OllamaModelsResponse> =>
    ipcRenderer.invoke('listOllamaModels', host),
  enhancePrompt: (request: EnhancePromptRequest): Promise<EnhancePromptResponse> =>
    ipcRenderer.invoke('enhancePrompt', request),
  generateAction: (request: GenerateActionRequest): Promise<GenerateActionResponse> =>
    ipcRenderer.invoke('generateAction', request),
  getRegistry: (): Promise<RegistrySummary> => ipcRenderer.invoke('getRegistry'),
  rescanRegistry: (): Promise<
    { ok: true; registry: RegistrySummary } | { ok: false; error: string }
  > => ipcRenderer.invoke('rescanRegistry'),
  pickAssetFile: (kind: 'scene' | 'character'): Promise<PickAssetFileResponse> =>
    ipcRenderer.invoke('pickAssetFile', kind),
  addScene: (request: AddSceneRequest): Promise<AddAssetResponse> =>
    ipcRenderer.invoke('addScene', request),
  addCharacter: (request: AddCharacterRequest): Promise<AddAssetResponse> =>
    ipcRenderer.invoke('addCharacter', request),
  removeScene: (id: string): Promise<{ ok: true } | { ok: false; error: string }> =>
    ipcRenderer.invoke('removeScene', id),
  removeCharacter: (id: string): Promise<{ ok: true } | { ok: false; error: string }> =>
    ipcRenderer.invoke('removeCharacter', id),
  pickCharacterFolder: (): Promise<PickCharacterFolderResponse> =>
    ipcRenderer.invoke('pickAssetFolder', 'character'),
  pickSceneFolder: (): Promise<PickSceneFolderResponse> =>
    ipcRenderer.invoke('pickAssetFolder', 'scene'),
  updateCharacter: (
    request: UpdateCharacterRequest
  ): Promise<{ ok: true } | { ok: false; error: string }> =>
    ipcRenderer.invoke('updateCharacter', request),
  updateScene: (
    request: UpdateSceneRequest
  ): Promise<{ ok: true } | { ok: false; error: string }> =>
    ipcRenderer.invoke('updateScene', request),
  saveProject: (
    payload: Omit<ProjectFile, 'version' | 'savedAt'>
  ): Promise<SaveProjectResponse> => ipcRenderer.invoke('saveProject', payload),
  openProject: (): Promise<OpenProjectResponse> => ipcRenderer.invoke('openProject'),
  onRenderStatus: (callback: (event: RenderStatusEvent) => void): (() => void) => {
    const listener = (_e: Electron.IpcRendererEvent, payload: RenderStatusEvent): void =>
      callback(payload)
    ipcRenderer.on('render-status', listener)
    return () => {
      ipcRenderer.off('render-status', listener)
    }
  },
  getDaemonState: (): Promise<{ state: DaemonState; port?: number }> =>
    ipcRenderer.invoke('getDaemonState'),
  restartDaemon: (): Promise<{ ok: true } | { ok: false; error: string }> =>
    ipcRenderer.invoke('restartDaemon'),
  onDaemonStatus: (callback: (event: DaemonStatusEvent) => void): (() => void) => {
    const listener = (_e: Electron.IpcRendererEvent, payload: DaemonStatusEvent): void =>
      callback(payload)
    ipcRenderer.on('daemon-status', listener)
    return () => {
      ipcRenderer.off('daemon-status', listener)
    }
  }
}

if (process.contextIsolated) {
  try {
    contextBridge.exposeInMainWorld('electron', electronAPI)
    contextBridge.exposeInMainWorld('veraframe', veraframe)
  } catch (error) {
    console.error(error)
  }
} else {
  // @ts-ignore (define in dts)
  window.electron = electronAPI
  // @ts-ignore (define in dts)
  window.veraframe = veraframe
}

export type Veraframe = typeof veraframe
