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

export type DaemonState = 'starting' | 'ready' | 'crashed' | 'restarting' | 'stopped'

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
  /** Live port the daemon is listening on (may change across restarts). */
  readonly port: number
  /** Current health state. */
  getState(): DaemonState
  /** Subscribe to state changes; returns an unsubscribe function. */
  onStateChange(listener: (state: DaemonState, detail?: string) => void): () => void
  call<T = unknown>(method: string, params?: Record<string, unknown>): Promise<T>
  /** Force a restart (e.g., user pressed a "Restart daemon" button). */
  restart(): Promise<void>
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
  /**
   * Auto-restart on unexpected exit. When false the handle transitions to
   * 'crashed' and stays there until the caller invokes restart(). Default: true.
   */
  autoRestart?: boolean
}

/**
 * Spawn the Blender daemon and resolve with a handle once it's accepting
 * connections. The handle owns the child process and auto-restarts on
 * unexpected exit (Blender crash, OOM kill, etc.) unless `autoRestart: false`.
 */
export async function startDaemon(options: StartDaemonOptions = {}): Promise<DaemonHandle> {
  const blenderPath = options.blenderPath ?? findBlender()
  const daemonScript = options.daemonScript ?? resolveDaemonScript()
  const startupTimeoutMs = options.startupTimeoutMs ?? 60_000
  const autoRestart = options.autoRestart ?? true

  const listeners = new Set<(state: DaemonState, detail?: string) => void>()
  let state: DaemonState = 'starting'
  const setState = (next: DaemonState, detail?: string): void => {
    if (state === next) return
    state = next
    console.log(`[daemon] state → ${next}${detail ? ` (${detail})` : ''}`)
    for (const cb of listeners) cb(next, detail)
  }

  let child: ChildProcess
  let port: number
  let shuttingDown = false

  const launch = async (): Promise<void> => {
    port = options.port ?? (await pickFreePort())
    child = spawn(
      blenderPath,
      ['--background', '--python', daemonScript, '--', '--port', String(port)],
      { stdio: ['ignore', 'pipe', 'pipe'] }
    )
    if (child.stdout) forwardLines(child.stdout, '[blender]', process.stdout)
    if (child.stderr) forwardLines(child.stderr, '[blender]', process.stderr)

    interface ExitInfo {
      code: number | null
      signal: NodeJS.Signals | null
    }
    // Use a single-element array so TS doesn't aggressively narrow the
    // closure-captured `null` literal — we mutate from the listener.
    const earlyExit: [ExitInfo | null] = [null]
    const onEarlyExit = (code: number | null, signal: NodeJS.Signals | null): void => {
      earlyExit[0] = { code, signal }
    }
    child.once('exit', onEarlyExit)

    const deadline = Date.now() + startupTimeoutMs
    while (Date.now() < deadline) {
      const exit = earlyExit[0]
      if (exit) {
        throw new DaemonError(
          `Blender exited before daemon was ready (code=${exit.code} signal=${exit.signal})`
        )
      }
      if (await ping(port)) {
        // Swap the early-exit listener for the long-lived crash listener.
        child.removeListener('exit', onEarlyExit)
        child.once('exit', (code, signal) => {
          if (shuttingDown) {
            setState('stopped')
            return
          }
          const detail = `code=${code} signal=${signal}`
          setState('crashed', detail)
          if (autoRestart) {
            // Restart asynchronously with a short backoff so we don't busy-loop
            // on persistent failures.
            setTimeout(() => {
              void restartInternal().catch((err) => {
                console.error('[daemon] restart failed:', err)
                setState('crashed', (err as Error).message)
              })
            }, 2_000)
          }
        })
        setState('ready', `port=${port}`)
        return
      }
      await delay(250)
    }
    child.kill('SIGTERM')
    throw new DaemonError(`daemon did not become ready within ${startupTimeoutMs}ms`)
  }

  const restartInternal = async (): Promise<void> => {
    if (shuttingDown) return
    setState('restarting')
    await launch()
  }

  await launch()

  return {
    get port(): number {
      return port
    },
    getState: () => state,
    onStateChange(listener) {
      listeners.add(listener)
      // Fire the current state immediately so subscribers don't miss it.
      listener(state)
      return () => listeners.delete(listener)
    },
    async call<T>(method: string, params: Record<string, unknown> = {}): Promise<T> {
      if (state !== 'ready') {
        throw new DaemonError(`daemon is ${state}, not ready`)
      }
      return rpcCall<T>(port, method, params)
    },
    async restart(): Promise<void> {
      if (shuttingDown) return
      if (child && child.exitCode === null) {
        child.kill('SIGTERM')
        await Promise.race([waitForExit(child), delay(5_000)])
        if (child.exitCode === null) child.kill('SIGKILL')
      }
      await restartInternal()
    },
    async shutdown(): Promise<void> {
      if (shuttingDown || (child && child.exitCode !== null)) return
      shuttingDown = true
      child.kill('SIGTERM')
      await Promise.race([waitForExit(child), delay(5_000)])
      if (child.exitCode === null) {
        child.kill('SIGKILL')
        await waitForExit(child)
      }
      setState('stopped')
    }
  }
}

function forwardLines(
  stream: NodeJS.ReadableStream,
  prefix: string,
  sink: NodeJS.WriteStream
): void {
  let buf = ''
  stream.on('data', (chunk: Buffer | string) => {
    buf += typeof chunk === 'string' ? chunk : chunk.toString('utf8')
    let newline: number
    while ((newline = buf.indexOf('\n')) >= 0) {
      const line = buf.slice(0, newline)
      buf = buf.slice(newline + 1)
      sink.write(`${prefix} ${line}\n`)
    }
  })
  stream.on('end', () => {
    if (buf) sink.write(`${prefix} ${buf}\n`)
  })
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
