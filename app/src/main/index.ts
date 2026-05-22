import { app, shell, BrowserWindow, ipcMain, protocol, dialog } from 'electron'
import { createReadStream } from 'fs'
import { copyFile, stat } from 'fs/promises'
import { join } from 'path'
import { Readable } from 'stream'
import { electronApp, optimizer, is } from '@electron-toolkit/utils'
import icon from '../../resources/icon.png?asset'
import { startDaemon, type DaemonHandle } from './daemon'
import { loadAssets, resolveAssetsDir, type AssetRegistry } from './assets'
import { buildMockTimeline } from './mock'
import { runTimeline, type RenderResult } from './render'
import { runPlanner, runEnhance, resolveRepoRoot } from './planner'

let daemonHandle: DaemonHandle | null = null
let assets: AssetRegistry | null = null

/**
 * Map of renderId → MP4 path on disk. The custom `veraframe-render://` protocol
 * resolves URLs against this map so the renderer can play the file without
 * needing direct filesystem access.
 */
const renderedVideos = new Map<string, string>()

export type LLMProvider = 'openai' | 'anthropic' | 'gemini' | 'ollama'

export interface RenderRequest {
  mode: 'mock' | 'llm'
  prompt?: string
  durationSec?: number
  provider?: LLMProvider
  model?: string
  ollamaHost?: string
}

interface RenderSuccess {
  ok: true
  renderId: string
  videoUrl: string
  durationSec: number
  executed: number
  skipped: number
  timeline: Record<string, unknown>
}

interface RenderFailure {
  ok: false
  error: string
}

type RenderResponse = RenderSuccess | RenderFailure

// Custom protocol must be registered before app.whenReady().
protocol.registerSchemesAsPrivileged([
  {
    scheme: 'veraframe-render',
    privileges: { standard: true, secure: true, supportFetchAPI: true, stream: true }
  }
])

function createWindow(): void {
  // Create the browser window.
  const mainWindow = new BrowserWindow({
    width: 900,
    height: 670,
    show: false,
    autoHideMenuBar: true,
    ...(process.platform === 'linux' ? { icon } : {}),
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: false
    }
  })

  mainWindow.on('ready-to-show', () => {
    mainWindow.show()
  })

  mainWindow.webContents.setWindowOpenHandler((details) => {
    shell.openExternal(details.url)
    return { action: 'deny' }
  })

  // HMR for renderer base on electron-vite cli.
  // Load the remote URL for development or the local html file for production.
  if (is.dev && process.env['ELECTRON_RENDERER_URL']) {
    mainWindow.loadURL(process.env['ELECTRON_RENDERER_URL'])
  } else {
    mainWindow.loadFile(join(__dirname, '../renderer/index.html'))
  }
}

// This method will be called when Electron has finished
// initialization and is ready to create browser windows.
// Some APIs can only be used after this event occurs.
app.whenReady().then(async () => {
  electronApp.setAppUserModelId('com.electron')

  app.on('browser-window-created', (_, window) => {
    optimizer.watchWindowShortcuts(window)
  })

  ipcMain.on('ping', () => console.log('pong'))

  // Serve rendered MP4s under veraframe-render://<id>/video.mp4.
  // Implements HTTP Range requests so the <video> element can seek. Without
  // Range support every video.currentTime = T request returns the whole file
  // and the browser resets playback to 0 — breaking both the timeline scrubber
  // and the native player controls.
  protocol.handle('veraframe-render', async (request) => {
    const url = new URL(request.url)
    const renderId = url.hostname
    const filePath = renderedVideos.get(renderId)
    if (!filePath) {
      return new Response('not found', { status: 404 })
    }
    let fileSize: number
    try {
      const info = await stat(filePath)
      fileSize = info.size
    } catch {
      return new Response('file missing', { status: 404 })
    }

    const rangeHeader = request.headers.get('range')
    const rangeMatch = rangeHeader ? rangeHeader.match(/bytes=(\d+)-(\d*)/) : null
    if (rangeMatch) {
      const start = Number.parseInt(rangeMatch[1], 10)
      const end = rangeMatch[2] ? Number.parseInt(rangeMatch[2], 10) : fileSize - 1
      const safeEnd = Math.min(end, fileSize - 1)
      const chunkSize = safeEnd - start + 1
      const stream = createReadStream(filePath, { start, end: safeEnd })
      return new Response(Readable.toWeb(stream) as ReadableStream, {
        status: 206,
        headers: {
          'Content-Type': 'video/mp4',
          'Accept-Ranges': 'bytes',
          'Content-Range': `bytes ${start}-${safeEnd}/${fileSize}`,
          'Content-Length': String(chunkSize)
        }
      })
    }

    // Full-file response — also advertise Accept-Ranges so the browser knows
    // it can issue Range requests for subsequent seeks.
    const stream = createReadStream(filePath)
    return new Response(Readable.toWeb(stream) as ReadableStream, {
      status: 200,
      headers: {
        'Content-Type': 'video/mp4',
        'Accept-Ranges': 'bytes',
        'Content-Length': String(fileSize)
      }
    })
  })

  // Load asset registry — used to build mock timelines and resolve fbx paths.
  try {
    assets = loadAssets(resolveAssetsDir())
    console.log(
      `Assets loaded: ${Object.keys(assets.scenes).length} scene(s), ` +
        `${Object.keys(assets.characters).length} character(s), ` +
        `${Object.keys(assets.animations).length} animation(s)`
    )
  } catch (err) {
    console.error('Asset load failed:', err)
  }

  // Spawn the long-lived Blender daemon. If it fails, the app still opens —
  // the render handlers will surface the error to the renderer.
  try {
    daemonHandle = await startDaemon()
    console.log(`Blender daemon ready on port ${daemonHandle.port}`)
  } catch (err) {
    console.error('Blender daemon failed to start:', err)
  }

  ipcMain.handle('render', async (_event, request: RenderRequest): Promise<RenderResponse> => {
    if (!daemonHandle) return { ok: false, error: 'Blender daemon is not running' }
    if (!assets) return { ok: false, error: 'asset registry not loaded' }
    try {
      let timeline: Record<string, unknown>
      if (request.mode === 'mock') {
        timeline = buildMockTimeline(assets, request.durationSec ?? 8)
      } else {
        if (!request.prompt || !request.prompt.trim()) {
          return { ok: false, error: 'LLM mode requires a prompt' }
        }
        timeline = await runPlanner(request.prompt, resolveRepoRoot(), assets.assetsDir, {
          provider: request.provider,
          model: request.model,
          ollamaHost: request.ollamaHost
        })
      }
      const result: RenderResult = await runTimeline(daemonHandle, assets, timeline)
      renderedVideos.set(result.renderId, result.videoPath)
      return {
        ok: true,
        renderId: result.renderId,
        videoUrl: `veraframe-render://${result.renderId}/video.mp4`,
        durationSec: result.durationSec,
        executed: result.executed,
        skipped: result.skipped,
        timeline: result.timeline
      }
    } catch (err) {
      return { ok: false, error: (err as Error).message }
    }
  })

  ipcMain.handle(
    'enhancePrompt',
    async (
      _event,
      request: { prompt: string; provider?: LLMProvider; model?: string; ollamaHost?: string }
    ): Promise<{ ok: true; prompt: string } | { ok: false; error: string }> => {
      if (!assets) return { ok: false, error: 'asset registry not loaded' }
      if (!request.prompt?.trim()) return { ok: false, error: 'prompt is empty' }
      try {
        const enhanced = await runEnhance(request.prompt, resolveRepoRoot(), assets.assetsDir, {
          provider: request.provider,
          model: request.model,
          ollamaHost: request.ollamaHost
        })
        return { ok: true, prompt: enhanced }
      } catch (err) {
        return { ok: false, error: (err as Error).message }
      }
    }
  )

  ipcMain.handle(
    'listOllamaModels',
    async (
      _event,
      host: string
    ): Promise<{ ok: true; models: string[] } | { ok: false; error: string }> => {
      const base = (host || 'http://localhost:11434').replace(/\/+$/, '')
      try {
        const response = await fetch(`${base}/api/tags`, {
          signal: AbortSignal.timeout(3_000)
        })
        if (!response.ok) {
          return { ok: false, error: `Ollama returned HTTP ${response.status}` }
        }
        const body = (await response.json()) as { models?: Array<{ name?: string }> }
        const names = (body.models ?? [])
          .map((m) => m.name)
          .filter((n): n is string => Boolean(n))
          .sort()
        return { ok: true, models: names }
      } catch (err) {
        return {
          ok: false,
          error: `Could not reach Ollama at ${base}: ${(err as Error).message}`
        }
      }
    }
  )

  ipcMain.handle(
    'saveRender',
    async (_event, renderId: string): Promise<{ ok: true; path: string } | { ok: false; error: string }> => {
      const source = renderedVideos.get(renderId)
      if (!source) return { ok: false, error: `unknown renderId: ${renderId}` }
      const result = await dialog.showSaveDialog({
        title: 'Save rendered video',
        defaultPath: `veraframe-${renderId.slice(0, 8)}.mp4`,
        filters: [{ name: 'MP4 Video', extensions: ['mp4'] }]
      })
      if (result.canceled || !result.filePath) {
        return { ok: false, error: 'save canceled' }
      }
      try {
        await copyFile(source, result.filePath)
        return { ok: true, path: result.filePath }
      } catch (err) {
        return { ok: false, error: (err as Error).message }
      }
    }
  )

  createWindow()

  app.on('activate', function () {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

app.on('before-quit', async (event) => {
  if (!daemonHandle) return
  event.preventDefault()
  const handle = daemonHandle
  daemonHandle = null
  try {
    await handle.shutdown()
  } catch (err) {
    console.error('Blender daemon shutdown error:', err)
  }
  app.quit()
})

// In this file you can include the rest of your app's specific main process
// code. You can also put them in separate files and require them here.
