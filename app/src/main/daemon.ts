import { spawn, ChildProcess } from 'child_process'
import { createServer } from 'net'
import { existsSync } from 'fs'
import { resolve as resolvePath } from 'path'
import { rpcCall, RpcError } from './rpc'

const MACOS_DEFAULT_BLENDER = '/Applications/Blender.app/Contents/MacOS/Blender'

export class DaemonError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'DaemonError'
  }
}

/**
 * Resolve the Blender executable, mirroring planner.daemon_runner.find_blender:
 *   1. $BLENDER_PATH if set and points at an existing file
 *   2. `blender` on $PATH
 *   3. macOS default install location
 */
export function findBlender(): string {
  const envPath = (process.env.BLENDER_PATH ?? '').trim()
  if (envPath) {
    if (!existsSync(envPath)) {
      throw new DaemonError(`BLENDER_PATH points to a nonexistent file: ${envPath}`)
    }
    return envPath
  }

  for (const dir of (process.env.PATH ?? '').split(':')) {
    if (!dir) continue
    const candidate = resolvePath(dir, 'blender')
    if (existsSync(candidate)) return candidate
  }

  if (existsSync(MACOS_DEFAULT_BLENDER)) return MACOS_DEFAULT_BLENDER

  throw new DaemonError(
    'Could not locate the Blender executable. Set BLENDER_PATH or add `blender` to PATH.'
  )
}

/** Ask the OS for a free local port. */
export function pickFreePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = createServer()
    server.unref()
    server.once('error', reject)
    server.listen(0, '127.0.0.1', () => {
      const address = server.address()
      if (address && typeof address === 'object') {
        const port = address.port
        server.close(() => resolve(port))
      } else {
        server.close(() => reject(new DaemonError('could not pick a free port')))
      }
    })
  })
}

export interface DaemonHandle {
  readonly port: number
  call<T = unknown>(method: string, params?: Record<string, unknown>): Promise<T>
  shutdown(): Promise<void>
}

export interface StartDaemonOptions {
  /** Override the Blender executable path. */
  blenderPath?: string
  /** Specific port to use. Default: pick a free one. */
  port?: number
  /** Override the daemon script path. Default: locate ../../../blender_daemon/daemon.py. */
  daemonScript?: string
  /** Max time to wait for the daemon to accept connections. */
  startupTimeoutMs?: number
}

/**
 * Spawn the Blender daemon and resolve with a handle once it's accepting
 * connections. The handle owns the child process; `shutdown()` terminates it.
 */
export async function startDaemon(options: StartDaemonOptions = {}): Promise<DaemonHandle> {
  const blender = options.blenderPath ?? findBlender()
  const port = options.port ?? (await pickFreePort())
  const startupTimeoutMs = options.startupTimeoutMs ?? 60_000
  // Resolve daemon.py relative to the repo root, which sits two levels up from
  // the bundled main process at <repo>/app/out/main/index.js (Electron-vite
  // build output). During `electron-vite dev` the dirname is the source
  // location instead. We let callers override via options.daemonScript.
  const daemonScript = options.daemonScript ?? resolveDaemonScript()

  const child = spawn(
    blender,
    ['--background', '--python', daemonScript, '--', '--port', String(port)],
    { stdio: ['ignore', 'pipe', 'pipe'] }
  )

  type ExitInfo = { code: number | null; signal: NodeJS.Signals | null }
  let earlyExit: ExitInfo | null = null
  child.once('exit', (code, signal) => {
    earlyExit = { code, signal }
  })

  const deadline = Date.now() + startupTimeoutMs
  const readEarlyExit = (): ExitInfo | null => earlyExit
  while (Date.now() < deadline) {
    const exited = readEarlyExit()
    if (exited) {
      throw new DaemonError(
        `Blender exited before daemon was ready (code=${exited.code} signal=${exited.signal})`
      )
    }
    if (await ping(port)) {
      return makeHandle(port, child)
    }
    await delay(250)
  }

  child.kill('SIGTERM')
  throw new DaemonError(`daemon did not become ready within ${startupTimeoutMs}ms`)
}

function makeHandle(port: number, child: ChildProcess): DaemonHandle {
  let shuttingDown = false
  return {
    port,
    async call<T>(method: string, params: Record<string, unknown> = {}): Promise<T> {
      return rpcCall<T>(port, method, params)
    },
    async shutdown(): Promise<void> {
      if (shuttingDown || child.exitCode !== null) return
      shuttingDown = true
      child.kill('SIGTERM')
      await Promise.race([waitForExit(child), delay(5_000)])
      if (child.exitCode === null) {
        child.kill('SIGKILL')
        await waitForExit(child)
      }
    }
  }
}

function waitForExit(child: ChildProcess): Promise<void> {
  return new Promise((resolve) => {
    if (child.exitCode !== null) return resolve()
    child.once('exit', () => resolve())
  })
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function ping(port: number): Promise<boolean> {
  try {
    await rpcCall(port, 'status', {}, { connectTimeoutMs: 500, timeoutMs: 2_000 })
    return true
  } catch (e) {
    if (e instanceof RpcError) return false
    return false
  }
}

function resolveDaemonScript(): string {
  // __dirname during dev: <repo>/app/out/main (electron-vite places dev output here too)
  // We expect blender_daemon/daemon.py to live at <repo>/blender_daemon/daemon.py.
  const candidates = [
    resolvePath(__dirname, '..', '..', '..', 'blender_daemon', 'daemon.py'),
    resolvePath(__dirname, '..', '..', 'blender_daemon', 'daemon.py'),
    resolvePath(process.cwd(), 'blender_daemon', 'daemon.py'),
    resolvePath(process.cwd(), '..', 'blender_daemon', 'daemon.py')
  ]
  for (const candidate of candidates) {
    if (existsSync(candidate)) return candidate
  }
  throw new DaemonError(
    `Could not locate blender_daemon/daemon.py. Tried:\n${candidates.join('\n')}`
  )
}
