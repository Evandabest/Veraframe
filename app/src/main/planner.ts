import { spawn } from 'child_process'
import { existsSync } from 'fs'
import { resolve as resolvePath } from 'path'

export class PlannerError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'PlannerError'
  }
}

/**
 * Invoke `python -m planner.run_planner --prompt ...` and return the timeline JSON.
 *
 * Runs the planner Python subprocess once per render — appropriate while LLM
 * latency dominates startup cost. Stdout carries the JSON, stderr carries
 * progress messages (logged to console).
 */
export function runPlanner(prompt: string, repoRoot: string, assetsDir: string): Promise<Record<string, unknown>> {
  return new Promise((resolve, reject) => {
    const args = [
      '--directory',
      repoRoot,
      'run',
      'python',
      '-m',
      'planner.run_planner',
      '--prompt',
      prompt,
      '--assets',
      assetsDir
    ]
    const child = spawn('uv', args, { stdio: ['ignore', 'pipe', 'pipe'] })
    let stdout = ''
    let stderr = ''
    child.stdout.on('data', (chunk) => {
      stdout += chunk.toString('utf8')
    })
    child.stderr.on('data', (chunk) => {
      const text = chunk.toString('utf8')
      stderr += text
      for (const line of text.split('\n')) {
        if (line.trim()) console.log(`[planner] ${line}`)
      }
    })
    child.once('error', (err) => {
      reject(new PlannerError(`uv spawn failed: ${err.message}`))
    })
    child.once('close', (code) => {
      if (code !== 0) {
        reject(new PlannerError(`planner exited with code ${code}: ${stderr.trim()}`))
        return
      }
      try {
        const timeline = JSON.parse(stdout) as Record<string, unknown>
        resolve(timeline)
      } catch (e) {
        reject(new PlannerError(`planner output was not JSON: ${(e as Error).message}`))
      }
    })
  })
}

/** Locate the repo root (the directory containing `pyproject.toml`). */
export function resolveRepoRoot(): string {
  const candidates = [
    resolvePath(__dirname, '..', '..', '..'),
    resolvePath(__dirname, '..', '..'),
    process.cwd(),
    resolvePath(process.cwd(), '..')
  ]
  for (const candidate of candidates) {
    if (existsSync(resolvePath(candidate, 'pyproject.toml'))) return candidate
  }
  throw new PlannerError(
    `Could not locate repo root (pyproject.toml). Tried:\n${candidates.join('\n')}`
  )
}
