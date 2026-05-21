import { Socket } from 'net'

export class RpcError extends Error {
  constructor(
    message: string,
    public readonly code?: number
  ) {
    super(message)
    this.name = 'RpcError'
  }
}

let nextId = 1

/**
 * Send one JSON-RPC 2.0 request over a fresh TCP connection and return the
 * `result` field. Mirrors `DaemonHandle.call` in planner/daemon_runner.py:
 * connect → send line-delimited request → read line-delimited response → close.
 *
 * `timeoutMs` caps how long we wait for the response after the request is
 * flushed. Pass `null` for "wait forever" — appropriate for renders that can
 * legitimately run for minutes.
 */
export function rpcCall<T = unknown>(
  port: number,
  method: string,
  params: Record<string, unknown> = {},
  options: { timeoutMs?: number | null; connectTimeoutMs?: number } = {}
): Promise<T> {
  const connectTimeoutMs = options.connectTimeoutMs ?? 10_000
  const timeoutMs = options.timeoutMs === undefined ? null : options.timeoutMs
  const id = nextId++
  const request = JSON.stringify({ jsonrpc: '2.0', id, method, params }) + '\n'

  return new Promise<T>((resolve, reject) => {
    const socket = new Socket()
    let buffer = ''
    let settled = false
    let responseTimer: NodeJS.Timeout | undefined

    const finish = (err: Error | null, value?: T): void => {
      if (settled) return
      settled = true
      if (responseTimer) clearTimeout(responseTimer)
      socket.destroy()
      if (err) reject(err)
      else resolve(value as T)
    }

    socket.setTimeout(connectTimeoutMs)
    socket.once('timeout', () => finish(new RpcError(`rpc ${method} connect timed out`)))
    socket.once('error', (err) => finish(new RpcError(`rpc ${method} socket error: ${err.message}`)))

    socket.connect(port, '127.0.0.1', () => {
      socket.setTimeout(0)
      if (timeoutMs !== null) {
        responseTimer = setTimeout(
          () => finish(new RpcError(`rpc ${method} response timed out`)),
          timeoutMs
        )
      }
      socket.write(request)
    })

    socket.on('data', (chunk) => {
      buffer += chunk.toString('utf8')
      const newline = buffer.indexOf('\n')
      if (newline === -1) return
      const line = buffer.slice(0, newline)
      try {
        const response = JSON.parse(line) as {
          result?: T
          error?: { code: number; message: string }
        }
        if (response.error) {
          finish(new RpcError(`daemon error on ${method}: ${response.error.message}`, response.error.code))
        } else {
          finish(null, response.result as T)
        }
      } catch (e) {
        finish(new RpcError(`rpc ${method} response parse error: ${(e as Error).message}`))
      }
    })

    socket.once('close', () => {
      if (!settled) finish(new RpcError(`rpc ${method}: daemon closed connection before responding`))
    })
  })
}
