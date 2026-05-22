import { app, shell, BrowserWindow, ipcMain, protocol, dialog } from 'electron'
import { copyFile, mkdir, open, readdir, readFile, rm, stat, writeFile } from 'fs/promises'
import { randomUUID } from 'crypto'
import { join, resolve as resolvePath } from 'path'
import { electronApp, optimizer, is } from '@electron-toolkit/utils'
import icon from '../../resources/icon.png?asset'
import { startDaemon, type DaemonHandle } from './daemon'
import { loadAssets, resolveAssetsDir, type AssetRegistry } from './assets'
// buildMockTimeline removed — mock mode now loads a pre-rendered fixture
// from assets/fixtures/ instead of building + rendering a canned timeline.
import { runTimeline, type RenderResult } from './render'
import { runPlanner, runEnhance, runActionGen, resolveRepoRoot } from './planner'

let daemonHandle: DaemonHandle | null = null
let assets: AssetRegistry | null = null

/**
 * Map of renderId → MP4 path on disk. The custom `veraframe-render://` protocol
 * resolves URLs against this map so the renderer can play the file without
 * needing direct filesystem access.
 */
const renderedVideos = new Map<string, string>()

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
  provider?: LLMProvider
  model?: string
  ollamaHost?: string
  /** Required when mode='direct'; an already-resolved timeline JSON. */
  timeline?: Record<string, unknown>
  /** Optional incremental config; only valid with mode='direct'. */
  incremental?: IncrementalRenderRequest
  /** Hard constraint: LLM mode only. Forces the scene id. */
  selectedScene?: string
  /** Hard constraint: LLM mode only. Limits the character pool. */
  selectedCharacters?: string[]
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
  // 206 Partial Content support, every video.currentTime = T request returns
  // the whole file from byte 0 and the browser resets playback to 0.
  protocol.handle('veraframe-render', async (request) => {
    const url = new URL(request.url)
    const renderId = url.hostname
    const filePath = renderedVideos.get(renderId)
    if (!filePath) {
      console.log(`[protocol] 404 ${request.url} (no path for renderId=${renderId})`)
      return new Response('not found', { status: 404 })
    }
    let fileSize: number
    try {
      const info = await stat(filePath)
      fileSize = info.size
    } catch {
      console.log(`[protocol] 404 ${request.url} (file missing: ${filePath})`)
      return new Response('file missing', { status: 404 })
    }

    const rangeHeader = request.headers.get('range')
    const rangeMatch = rangeHeader ? rangeHeader.match(/bytes=(\d+)-(\d*)/) : null
    if (rangeMatch) {
      const start = Number.parseInt(rangeMatch[1], 10)
      const end = rangeMatch[2] ? Number.parseInt(rangeMatch[2], 10) : fileSize - 1
      const safeEnd = Math.min(end, fileSize - 1)
      const chunkSize = safeEnd - start + 1
      const fh = await open(filePath, 'r')
      const buffer = Buffer.alloc(chunkSize)
      await fh.read(buffer, 0, chunkSize, start)
      await fh.close()
      console.log(
        `[protocol] 206 ${request.url} range=${start}-${safeEnd}/${fileSize} (${chunkSize}B)`
      )
      return new Response(buffer, {
        status: 206,
        headers: {
          'Content-Type': 'video/mp4',
          'Accept-Ranges': 'bytes',
          'Content-Range': `bytes ${start}-${safeEnd}/${fileSize}`,
          'Content-Length': String(chunkSize)
        }
      })
    }

    // Full-file response — advertise Accept-Ranges so the browser knows it can
    // issue Range requests for subsequent seeks.
    const fh = await open(filePath, 'r')
    const buffer = Buffer.alloc(fileSize)
    await fh.read(buffer, 0, fileSize, 0)
    await fh.close()
    console.log(`[protocol] 200 ${request.url} (full ${fileSize}B)`)
    return new Response(buffer, {
      status: 200,
      headers: {
        'Content-Type': 'video/mp4',
        'Accept-Ranges': 'bytes',
        'Content-Length': String(fileSize)
      }
    })
  })

  // Load asset registry. We merge the repo-bundled assets with a user-data
  // directory so users can upload their own scenes/characters and have them
  // persist across runs without modifying the repo.
  const userAssetsDir = resolvePath(app.getPath('userData'), 'assets')
  const reloadAssets = (): AssetRegistry => {
    const next = loadAssets(resolveAssetsDir(), userAssetsDir)
    console.log(
      `Assets loaded: ${Object.keys(next.scenes).length} scene(s), ` +
        `${Object.keys(next.characters).length} character(s), ` +
        `${Object.keys(next.animations).length} animation(s) ` +
        `(user dir: ${userAssetsDir})`
    )
    return next
  }
  try {
    assets = reloadAssets()
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

  ipcMain.handle('render', async (event, request: RenderRequest): Promise<RenderResponse> => {
    if (!daemonHandle) return { ok: false, error: 'Blender daemon is not running' }
    if (!assets) return { ok: false, error: 'asset registry not loaded' }
    const sendProgress = (step: string, detail?: string): void => {
      event.sender.send('render-status', { step, detail })
    }
    try {
      // Mock mode short-circuits the entire render pipeline: it loads a
      // pre-rendered MP4 + matching timeline from assets/fixtures/ and
      // returns immediately. Lets the user test the editor (and incremental
      // edits, which still render slices in Blender) without paying the
      // ~60s full-render cost on every page load.
      if (request.mode === 'mock') {
        sendProgress('load_fixture')
        try {
          const fixtureVideo = resolvePath(assets.assetsDir, 'fixtures', 'mock-classroom.mp4')
          const fixtureJson = resolvePath(assets.assetsDir, 'fixtures', 'mock-classroom.json')
          const timelineText = await readFile(fixtureJson, 'utf8')
          const fixtureTimeline = JSON.parse(timelineText) as Record<string, unknown>
          const shotsArr = (fixtureTimeline.shots as Array<Record<string, unknown>>) ?? []
          const fixtureDurationSec = Math.max(0, ...shotsArr.map((s) => Number(s.end ?? 0)))

          const renderId = randomUUID()
          renderedVideos.set(renderId, fixtureVideo)
          return {
            ok: true,
            renderId,
            videoUrl: `veraframe-render://${renderId}/video.mp4`,
            durationSec: fixtureDurationSec,
            executed: shotsArr.reduce(
              (n, s) => n + ((s.actions as unknown[] | undefined)?.length ?? 0),
              0
            ),
            skipped: 0,
            timeline: fixtureTimeline
          }
        } catch (err) {
          return {
            ok: false,
            error: `mock fixture load failed: ${(err as Error).message}`
          }
        }
      }

      let timeline: Record<string, unknown>
      if (request.mode === 'direct') {
        if (!request.timeline) {
          return { ok: false, error: 'direct mode requires a timeline' }
        }
        timeline = request.timeline
      } else if (request.mode === 'llm') {
        if (!request.prompt || !request.prompt.trim()) {
          return { ok: false, error: 'LLM mode requires a prompt' }
        }
        sendProgress('llm', `${request.provider ?? 'openai'}:${request.model ?? '(default)'}`)
        timeline = await runPlanner(request.prompt, resolveRepoRoot(), assets.assetsDir, {
          provider: request.provider,
          model: request.model,
          ollamaHost: request.ollamaHost,
          selectedScene: request.selectedScene,
          selectedCharacters: request.selectedCharacters
        })
      } else {
        return { ok: false, error: `unsupported mode: ${request.mode}` }
      }
      let incrementalConfig: import('./render').IncrementalRender | undefined
      if (request.incremental) {
        const prevPath = renderedVideos.get(request.incremental.previousRenderId)
        if (!prevPath) {
          return {
            ok: false,
            error: `previousRenderId not found: ${request.incremental.previousRenderId}`
          }
        }
        incrementalConfig = {
          previousVideoPath: prevPath,
          changedWindow: request.incremental.changedWindow,
          operation: request.incremental.operation
        }
      }
      const result: RenderResult = await runTimeline(daemonHandle, assets, timeline, {
        onProgress: ({ step, detail }) => sendProgress(step, detail),
        incremental: incrementalConfig
      })
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
    'generateAction',
    async (
      _event,
      request: {
        prompt: string
        scene: string
        character: string
        actionId: string
        start: number
        /** Optional; omit to let the LLM pick a duration. */
        end?: number
        timelineContext: Record<string, unknown>
        provider?: LLMProvider
        model?: string
      }
    ): Promise<{ ok: true; action: Record<string, unknown> } | { ok: false; error: string }> => {
      if (!assets) return { ok: false, error: 'asset registry not loaded' }
      if (!request.prompt?.trim()) return { ok: false, error: 'prompt is empty' }
      try {
        const action = await runActionGen(
          request.prompt,
          resolveRepoRoot(),
          assets.assetsDir,
          {
            scene: request.scene,
            character: request.character,
            actionId: request.actionId,
            start: request.start,
            end: request.end,
            context: request.timelineContext
          },
          { provider: request.provider, model: request.model }
        )
        return { ok: true, action }
      } catch (err) {
        return { ok: false, error: (err as Error).message }
      }
    }
  )

  // -------------------------------------------------------------------------
  // Registry IPC: list, rescan, and upload scenes/characters.
  // -------------------------------------------------------------------------

  const registrySummary = (
    reg: AssetRegistry | null
  ): {
    scenes: Array<{ id: string; displayName: string; spawnPoints: string[]; cameraPresets: string[]; userProvided: boolean }>
    characters: Array<{ id: string; displayName: string; userProvided: boolean }>
  } => {
    if (!reg) return { scenes: [], characters: [] }
    const userDir = reg.userAssetsDir
    return {
      scenes: Object.values(reg.scenes).map((s) => ({
        id: s.id,
        displayName: s.displayName,
        spawnPoints: s.spawnPoints,
        cameraPresets: s.cameraPresets,
        userProvided: Boolean(userDir && s.blendPath.startsWith(userDir))
      })),
      characters: Object.values(reg.characters).map((c) => ({
        id: c.id,
        displayName: c.displayName,
        userProvided: Boolean(userDir && c.meshPath.startsWith(userDir))
      }))
    }
  }

  ipcMain.handle('getRegistry', async () => registrySummary(assets))

  ipcMain.handle('rescanRegistry', async () => {
    try {
      assets = reloadAssets()
      return { ok: true, registry: registrySummary(assets) }
    } catch (err) {
      return { ok: false, error: (err as Error).message }
    }
  })

  ipcMain.handle(
    'pickAssetFolder',
    async (
      _event,
      kind: 'character' | 'scene'
    ): Promise<
      | {
          ok: true
          kind: 'character'
          folderPath: string
          mesh: string
          idle: string
          walk: string
          manifest: { id?: string; displayName?: string; description?: string } | null
        }
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
    > => {
      const result = await dialog.showOpenDialog({
        title:
          kind === 'character'
            ? 'Pick a character folder (character.fbx + idle.fbx + walk_in_place.fbx)'
            : 'Pick a scene folder (scene.blend or scene.fbx + optional scene.json)',
        properties: ['openDirectory']
      })
      if (result.canceled || !result.filePaths[0]) {
        return { ok: false, error: 'picker canceled' }
      }
      const folder = result.filePaths[0]
      try {
        const entries = (await readdir(folder)).filter((n) => !n.startsWith('.'))
        if (kind === 'character') {
          const fbxFiles = entries.filter((n) => n.toLowerCase().endsWith('.fbx'))
          const findBy = (predicate: (n: string) => boolean): string | null => {
            const hit = fbxFiles.find((n) => predicate(n.toLowerCase()))
            return hit ? resolvePath(folder, hit) : null
          }
          const idle =
            findBy((n) => n === 'idle.fbx') ?? findBy((n) => /(^|[^a-z])idle/.test(n))
          const walk =
            findBy((n) => n === 'walk_in_place.fbx' || n === 'walk.fbx') ??
            findBy((n) => /(^|[^a-z])walk/.test(n))
          const mesh =
            findBy((n) => n === 'character.fbx' || n === 'mesh.fbx') ??
            findBy((n) => !/(^|[^a-z])(idle|walk)/.test(n))
          if (!mesh || !idle || !walk) {
            const missing = [
              !mesh && 'mesh (.fbx)',
              !idle && 'idle.fbx',
              !walk && 'walk_in_place.fbx'
            ]
              .filter(Boolean)
              .join(', ')
            return { ok: false, error: `Folder is missing: ${missing}` }
          }
          let manifest: { id?: string; displayName?: string; description?: string } | null = null
          const manifestPath = resolvePath(folder, 'character.json')
          try {
            const raw = JSON.parse(await readFile(manifestPath, 'utf8')) as Record<
              string,
              unknown
            >
            manifest = {
              id: typeof raw.id === 'string' ? raw.id : undefined,
              displayName:
                typeof raw.display_name === 'string'
                  ? (raw.display_name as string)
                  : undefined,
              description:
                typeof raw.description === 'string' ? (raw.description as string) : undefined
            }
          } catch {
            /* no manifest is fine */
          }
          return { ok: true, kind: 'character', folderPath: folder, mesh, idle, walk, manifest }
        }
        // kind === 'scene'
        const sceneCandidates = entries.filter((n) => {
          const lower = n.toLowerCase()
          return lower.endsWith('.blend') || lower.endsWith('.fbx')
        })
        if (sceneCandidates.length === 0) {
          return { ok: false, error: 'Folder has no .blend or .fbx scene file.' }
        }
        // Prefer a file literally named scene.{blend,fbx}, then the first match.
        const preferred =
          sceneCandidates.find((n) => /^scene\.(blend|fbx)$/i.test(n)) ?? sceneCandidates[0]
        const sceneFile = resolvePath(folder, preferred)
        let manifest: {
          id?: string
          displayName?: string
          description?: string
          spawnPoints?: string[]
          cameraPresets?: string[]
          lightingPresets?: string[]
        } | null = null
        const manifestPath = resolvePath(folder, 'scene.json')
        try {
          const raw = JSON.parse(await readFile(manifestPath, 'utf8')) as Record<
            string,
            unknown
          >
          manifest = {
            id: typeof raw.id === 'string' ? raw.id : undefined,
            displayName:
              typeof raw.display_name === 'string' ? (raw.display_name as string) : undefined,
            description:
              typeof raw.description === 'string' ? (raw.description as string) : undefined,
            spawnPoints: Array.isArray(raw.spawn_points)
              ? (raw.spawn_points as string[])
              : undefined,
            cameraPresets: Array.isArray(raw.camera_presets)
              ? (raw.camera_presets as string[])
              : undefined,
            lightingPresets: Array.isArray(raw.lighting_presets)
              ? (raw.lighting_presets as string[])
              : undefined
          }
        } catch {
          /* no manifest is fine */
        }
        return { ok: true, kind: 'scene', folderPath: folder, sceneFile, manifest }
      } catch (err) {
        return { ok: false, error: (err as Error).message }
      }
    }
  )

  ipcMain.handle(
    'pickAssetFile',
    async (
      _event,
      kind: 'scene' | 'character'
    ): Promise<{ ok: true; filePath: string } | { ok: false; error: string }> => {
      const result = await dialog.showOpenDialog({
        title:
          kind === 'scene'
            ? 'Pick a scene file (.blend or .fbx)'
            : 'Pick a character / animation .fbx',
        properties: ['openFile'],
        filters:
          kind === 'scene'
            ? [
                { name: 'Scene file', extensions: ['blend', 'fbx'] },
                { name: 'Blender scene', extensions: ['blend'] },
                { name: 'FBX scene', extensions: ['fbx'] }
              ]
            : [{ name: 'FBX', extensions: ['fbx'] }]
      })
      if (result.canceled || !result.filePaths[0]) {
        return { ok: false, error: 'picker canceled' }
      }
      return { ok: true, filePath: result.filePaths[0] }
    }
  )

  ipcMain.handle(
    'addScene',
    async (
      _event,
      payload: {
        sourcePath: string
        id: string
        displayName: string
        description?: string
        spawnPoints: string[]
        cameraPresets: string[]
        lightingPresets?: string[]
      }
    ): Promise<{ ok: true; id: string } | { ok: false; error: string }> => {
      if (!/^[a-z0-9_]+$/i.test(payload.id)) {
        return { ok: false, error: "id must be alphanumeric / underscore only" }
      }
      const sceneDir = resolvePath(userAssetsDir, 'scenes', payload.id)
      try {
        await mkdir(sceneDir, { recursive: true })
        // Preserve the source extension so the daemon picks the right loader.
        // `.blend` opens via wm.open_mainfile; `.fbx` imports via import_scene.fbx.
        const sourceExt = payload.sourcePath
          .toLowerCase()
          .replace(/^.*\./, '')
        const ext = sourceExt === 'fbx' ? 'fbx' : 'blend'
        const sceneFile = `scene.${ext}`
        const destPath = resolvePath(sceneDir, sceneFile)
        await copyFile(payload.sourcePath, destPath)
        const manifest = {
          id: payload.id,
          display_name: payload.displayName,
          description: payload.description ?? '',
          blend_file: sceneFile,
          spawn_points: payload.spawnPoints,
          camera_presets: payload.cameraPresets,
          lighting_presets: payload.lightingPresets ?? ['default']
        }
        await writeFile(
          resolvePath(sceneDir, 'scene.json'),
          JSON.stringify(manifest, null, 2),
          'utf8'
        )
        assets = reloadAssets()
        return { ok: true, id: payload.id }
      } catch (err) {
        return { ok: false, error: (err as Error).message }
      }
    }
  )

  ipcMain.handle(
    'addCharacter',
    async (
      _event,
      payload: {
        sourcePath: string
        idlePath: string
        walkPath: string
        id: string
        displayName: string
        description?: string
      }
    ): Promise<{ ok: true; id: string } | { ok: false; error: string }> => {
      if (!/^[a-z0-9_]+$/i.test(payload.id)) {
        return { ok: false, error: "id must be alphanumeric / underscore only" }
      }
      const charDir = resolvePath(userAssetsDir, 'characters', payload.id)
      try {
        await mkdir(charDir, { recursive: true })
        const fbxDest = resolvePath(charDir, 'character.fbx')
        const idleDest = resolvePath(charDir, 'idle.fbx')
        const walkDest = resolvePath(charDir, 'walk_in_place.fbx')
        await copyFile(payload.sourcePath, fbxDest)
        await copyFile(payload.idlePath, idleDest)
        await copyFile(payload.walkPath, walkDest)
        const manifest = {
          id: payload.id,
          display_name: payload.displayName,
          description: payload.description ?? '',
          mesh_file: 'character.fbx',
          rig_type: 'mixamo',
          animations: {
            idle: 'idle.fbx',
            walk_in_place: 'walk_in_place.fbx'
          }
        }
        await writeFile(
          resolvePath(charDir, 'character.json'),
          JSON.stringify(manifest, null, 2),
          'utf8'
        )
        assets = reloadAssets()
        return { ok: true, id: payload.id }
      } catch (err) {
        return { ok: false, error: (err as Error).message }
      }
    }
  )

  // Per-file edit of an existing user-uploaded scene. Replaces the scene
  // file in place (preserving extension) and / or rewrites the manifest
  // fields. Bundled scenes can't be edited.
  ipcMain.handle(
    'updateScene',
    async (
      _event,
      payload: {
        id: string
        scenePath?: string | null
        displayName?: string | null
        description?: string | null
        spawnPoints?: string[] | null
        cameraPresets?: string[] | null
      }
    ): Promise<{ ok: true } | { ok: false; error: string }> => {
      if (!assets) return { ok: false, error: 'asset registry not loaded' }
      const existing = assets.scenes[payload.id]
      if (!existing) return { ok: false, error: `scene '${payload.id}' not found` }
      if (!existing.blendPath.startsWith(userAssetsDir)) {
        return { ok: false, error: `'${payload.id}' is bundled and cannot be edited` }
      }
      const sceneDir = resolvePath(existing.blendPath, '..')
      try {
        const manifestPath = resolvePath(sceneDir, 'scene.json')
        let manifest: Record<string, unknown> = {}
        try {
          manifest = JSON.parse(await readFile(manifestPath, 'utf8'))
        } catch {
          /* will write fresh if missing */
        }
        if (payload.scenePath) {
          const ext = payload.scenePath.toLowerCase().endsWith('.fbx') ? 'fbx' : 'blend'
          // Delete the previous scene file if its extension changed.
          const prevName = String(manifest.blend_file ?? 'scene.blend')
          if (prevName && !prevName.endsWith(`.${ext}`)) {
            await rm(resolvePath(sceneDir, prevName), { force: true })
          }
          const sceneFile = `scene.${ext}`
          await copyFile(payload.scenePath, resolvePath(sceneDir, sceneFile))
          manifest.blend_file = sceneFile
        }
        manifest.id = payload.id
        if (payload.displayName) manifest.display_name = payload.displayName
        if (payload.description !== undefined && payload.description !== null) {
          manifest.description = payload.description
        }
        if (payload.spawnPoints) manifest.spawn_points = payload.spawnPoints
        if (payload.cameraPresets) manifest.camera_presets = payload.cameraPresets
        await writeFile(manifestPath, JSON.stringify(manifest, null, 2), 'utf8')
        assets = reloadAssets()
        return { ok: true }
      } catch (err) {
        return { ok: false, error: (err as Error).message }
      }
    }
  )

  // Per-file edit of an existing user-uploaded character. Any of mesh / idle
  // / walk / displayName can be changed; null/undefined entries keep the
  // current value.
  ipcMain.handle(
    'updateCharacter',
    async (
      _event,
      payload: {
        id: string
        meshPath?: string | null
        idlePath?: string | null
        walkPath?: string | null
        displayName?: string | null
        description?: string | null
      }
    ): Promise<{ ok: true } | { ok: false; error: string }> => {
      if (!assets) return { ok: false, error: 'asset registry not loaded' }
      const existing = assets.characters[payload.id]
      if (!existing) return { ok: false, error: `character '${payload.id}' not found` }
      if (!existing.meshPath.startsWith(userAssetsDir)) {
        return { ok: false, error: `'${payload.id}' is bundled and cannot be edited` }
      }
      const charDir = resolvePath(existing.meshPath, '..')
      try {
        if (payload.meshPath) {
          await copyFile(payload.meshPath, resolvePath(charDir, 'character.fbx'))
        }
        if (payload.idlePath) {
          await copyFile(payload.idlePath, resolvePath(charDir, 'idle.fbx'))
        }
        if (payload.walkPath) {
          await copyFile(payload.walkPath, resolvePath(charDir, 'walk_in_place.fbx'))
        }
        // Rewrite manifest with any metadata changes; keep file refs stable.
        const manifestPath = resolvePath(charDir, 'character.json')
        let manifest: Record<string, unknown> = {}
        try {
          manifest = JSON.parse(await readFile(manifestPath, 'utf8'))
        } catch {
          /* if missing, we'll write a fresh one */
        }
        manifest.id = payload.id
        if (payload.displayName) manifest.display_name = payload.displayName
        if (payload.description !== undefined && payload.description !== null) {
          manifest.description = payload.description
        }
        manifest.mesh_file = 'character.fbx'
        manifest.rig_type = manifest.rig_type ?? 'mixamo'
        manifest.animations = {
          idle: 'idle.fbx',
          walk_in_place: 'walk_in_place.fbx'
        }
        await writeFile(manifestPath, JSON.stringify(manifest, null, 2), 'utf8')
        assets = reloadAssets()
        return { ok: true }
      } catch (err) {
        return { ok: false, error: (err as Error).message }
      }
    }
  )

  // Asset removal — only allowed for user-provided entries (those whose paths
  // live under userAssetsDir). The repo-bundled assets are read-only from the
  // app's perspective.
  const removeAsset = async (
    kind: 'scene' | 'character',
    id: string
  ): Promise<{ ok: true } | { ok: false; error: string }> => {
    if (!assets) return { ok: false, error: 'asset registry not loaded' }
    const target =
      kind === 'scene'
        ? assets.scenes[id]?.blendPath
        : assets.characters[id]?.meshPath
    if (!target) return { ok: false, error: `${kind} '${id}' not found` }
    if (!target.startsWith(userAssetsDir)) {
      return { ok: false, error: `${kind} '${id}' is a bundled asset and cannot be removed` }
    }
    const folder = resolvePath(target, '..')
    try {
      await rm(folder, { recursive: true, force: true })
      assets = reloadAssets()
      return { ok: true }
    } catch (err) {
      return { ok: false, error: (err as Error).message }
    }
  }

  ipcMain.handle('removeScene', async (_event, id: string) => removeAsset('scene', id))
  ipcMain.handle('removeCharacter', async (_event, id: string) => removeAsset('character', id))

  // -------------------------------------------------------------------------
  // Project file (.veraframe) save / open.
  //
  // A project is a snapshot of editor state — scene + character selections,
  // prompt + provider/model, and the last-rendered timeline JSON (if any).
  // The rendered video is NOT bundled; it lives in tmpdir and is regenerated
  // on demand. Opening a project with a stored timeline triggers a direct-
  // mode re-render to materialize the MP4.
  // -------------------------------------------------------------------------

  interface ProjectFile {
    version: 1
    /** ISO timestamp when this project was saved. */
    savedAt: string
    selectedScene: string | null
    selectedCharacters: string[]
    prompt: string
    mode: 'mock' | 'llm'
    provider: string
    model: string
    /** Optional last-rendered timeline JSON. */
    timeline: Record<string, unknown> | null
  }

  ipcMain.handle(
    'saveProject',
    async (
      _event,
      payload: Omit<ProjectFile, 'version' | 'savedAt'>
    ): Promise<{ ok: true; path: string } | { ok: false; error: string }> => {
      const result = await dialog.showSaveDialog({
        title: 'Save project',
        defaultPath: 'untitled.veraframe',
        filters: [{ name: 'Veraframe project', extensions: ['veraframe', 'json'] }]
      })
      if (result.canceled || !result.filePath) {
        return { ok: false, error: 'save canceled' }
      }
      try {
        const file: ProjectFile = {
          version: 1,
          savedAt: new Date().toISOString(),
          ...payload
        }
        await writeFile(result.filePath, JSON.stringify(file, null, 2), 'utf8')
        return { ok: true, path: result.filePath }
      } catch (err) {
        return { ok: false, error: (err as Error).message }
      }
    }
  )

  ipcMain.handle(
    'openProject',
    async (): Promise<{ ok: true; project: ProjectFile; path: string } | { ok: false; error: string }> => {
      const result = await dialog.showOpenDialog({
        title: 'Open project',
        properties: ['openFile'],
        filters: [{ name: 'Veraframe project', extensions: ['veraframe', 'json'] }]
      })
      if (result.canceled || !result.filePaths[0]) {
        return { ok: false, error: 'open canceled' }
      }
      try {
        const raw = await readFile(result.filePaths[0], 'utf8')
        const parsed = JSON.parse(raw) as ProjectFile
        if (parsed.version !== 1) {
          return { ok: false, error: `unsupported project version: ${parsed.version}` }
        }
        return { ok: true, project: parsed, path: result.filePaths[0] }
      } catch (err) {
        return { ok: false, error: (err as Error).message }
      }
    }
  )

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
