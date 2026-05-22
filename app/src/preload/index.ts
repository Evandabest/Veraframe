import { contextBridge, ipcRenderer } from 'electron'
import { electronAPI } from '@electron-toolkit/preload'

export interface RenderRequest {
  mode: 'mock' | 'llm'
  prompt?: string
  durationSec?: number
}

export type RenderResponse =
  | {
      ok: true
      renderId: string
      videoUrl: string
      durationSec: number
      executed: number
      skipped: number
    }
  | { ok: false; error: string }

export type SaveRenderResponse = { ok: true; path: string } | { ok: false; error: string }

/** API surface exposed on `window.veraframe` for the React renderer. */
const veraframe = {
  render: (request: RenderRequest): Promise<RenderResponse> =>
    ipcRenderer.invoke('render', request),
  saveRender: (renderId: string): Promise<SaveRenderResponse> =>
    ipcRenderer.invoke('saveRender', renderId)
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
