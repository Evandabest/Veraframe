import { spawn } from 'child_process'
import { existsSync } from 'fs'
import { resolve as resolvePath } from 'path'

export class PlannerError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'PlannerError'
  }
}

export interface PlannerOptions {
  /** LiteLLM provider id; sets VERAFRAME_LLM_PROVIDER for the subprocess. */
  provider?: string
  /** Model name (no provider prefix); sets VERAFRAME_LLM_MODEL. */
  model?: string
  /** Ollama API base; sets OLLAMA_API_BASE so LiteLLM hits the right host. */
  ollamaHost?: string
}

/**
 * Invoke `python -m planner.run_planner --prompt ...` and return the timeline JSON.
 *
 * Runs the planner Python subprocess once per render — appropriate while LLM
 * latency dominates startup cost. Stdout carries the JSON, stderr carries
 * progress messages (logged to console). Provider/model selection is passed
 * via env vars that LiteLLM (and `planner.LLMConfig.from_env`) read.
 */
export function runPlanner(
  prompt: string,
  repoRoot: string,
  assetsDir: string,
  options: PlannerOptions = {}
): Promise<Record<string, unknown>> {
  return runPythonEntry<Record<string, unknown>>(
    'planner.run_planner',
    prompt,
    repoRoot,
    assetsDir,
    options,
    (stdout) => JSON.parse(stdout) as Record<string, unknown>
  )
}

/**
 * Invoke `python -m planner.run_enhance` and return the rewritten prompt as
 * plain text. Same env-var plumbing as runPlanner so the enhance call uses the
 * same provider/model the user has selected.
 */
export function runEnhance(
  prompt: string,
  repoRoot: string,
  assetsDir: string,
  options: PlannerOptions = {}
): Promise<string> {
  return runPythonEntry<string>(
    'planner.run_enhance',
    prompt,
    repoRoot,
    assetsDir,
    options,
    (stdout) => stdout.trim()
  )
}

export interface ActionGenContext {
  scene: string
  character: string
  actionId: string
  start: number
  /** Optional. When provided, locks the action's end time (edit flow).
   *  Omitted, the LLM picks an end time based on the action it chooses. */
  end?: number
  /** Full timeline JSON so the LLM can see other characters / sibling actions. */
  context: Record<string, unknown>
}

/**
 * Invoke `python -m planner.run_action` to regenerate a single action from a
 * natural-language prompt. The caller's character/start/end/id are enforced
 * server-side, so the LLM only chooses the action type and its parameters.
 */
export function runActionGen(
  prompt: string,
  repoRoot: string,
  assetsDir: string,
  actionCtx: ActionGenContext,
  options: PlannerOptions = {}
): Promise<Record<string, unknown>> {
  const extraArgs = [
    '--scene', actionCtx.scene,
    '--character', actionCtx.character,
    '--action-id', actionCtx.actionId,
    '--start', String(actionCtx.start),
    '--context-json', JSON.stringify(actionCtx.context)
  ]
  if (actionCtx.end !== undefined) {
    extraArgs.push('--end', String(actionCtx.end))
  }
  return runPythonEntry<Record<string, unknown>>(
    'planner.run_action',
    prompt,
    repoRoot,
    assetsDir,
    options,
    (stdout) => JSON.parse(stdout) as Record<string, unknown>,
    extraArgs
  )
}

function runPythonEntry<T>(
  module: string,
  prompt: string,
  repoRoot: string,
  assetsDir: string,
  options: PlannerOptions,
  parseStdout: (stdout: string) => T,
  extraArgs: string[] = []
): Promise<T> {
  return new Promise((resolve, reject) => {
    const args = [
      '--directory',
      repoRoot,
      'run',
      'python',
      '-m',
      module,
      '--prompt',
      prompt,
      '--assets',
      assetsDir,
      ...extraArgs
    ]
    const env: NodeJS.ProcessEnv = { ...process.env }
    if (options.provider) env.VERAFRAME_LLM_PROVIDER = options.provider
    if (options.model) env.VERAFRAME_LLM_MODEL = options.model
    if (options.ollamaHost) env.OLLAMA_API_BASE = options.ollamaHost
    // Silence LiteLLM's import-time WARNING noise (bedrock/sagemaker pre-load
    // hints, etc.). The validator still surfaces real errors via stderr.
    env.LITELLM_LOG = env.LITELLM_LOG ?? 'ERROR'
    const child = spawn('uv', args, { stdio: ['ignore', 'pipe', 'pipe'], env })
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
        reject(new PlannerError(`${module} exited with code ${code}: ${stderr.trim()}`))
        return
      }
      try {
        resolve(parseStdout(stdout))
      } catch (e) {
        reject(new PlannerError(`${module} output unparsable: ${(e as Error).message}`))
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
