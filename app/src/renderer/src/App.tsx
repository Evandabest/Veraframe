import { useEffect, useRef, useState } from 'react'
import { TimelinePanel } from './components/TimelinePanel'

type LLMProvider = 'openai' | 'anthropic' | 'gemini' | 'ollama'

const PROVIDER_DEFAULT_MODEL: Record<LLMProvider, string> = {
  openai: 'gpt-4o',
  anthropic: 'claude-3-5-sonnet-20241022',
  gemini: 'gemini-1.5-pro',
  ollama: 'llama3.1'
}

const PROVIDER_LABEL: Record<LLMProvider, string> = {
  openai: 'OpenAI',
  anthropic: 'Anthropic',
  gemini: 'Google Gemini',
  ollama: 'Ollama (local)'
}

type RenderState =
  | { status: 'idle' }
  | { status: 'running' }
  | {
      status: 'success'
      renderId: string
      videoUrl: string
      durationSec: number
      timeline: Record<string, unknown>
    }
  | { status: 'error'; message: string }

function App(): React.JSX.Element {
  const [mode, setMode] = useState<'mock' | 'llm'>('mock')
  const [prompt, setPrompt] = useState('')
  const [provider, setProvider] = useState<LLMProvider>('openai')
  const [model, setModel] = useState<string>(PROVIDER_DEFAULT_MODEL.openai)
  // Hardcoded localhost; advanced users can set OLLAMA_API_BASE in their shell.
  const ollamaHost = 'http://localhost:11434'
  const [ollamaModels, setOllamaModels] = useState<string[] | null>(null)
  const [ollamaError, setOllamaError] = useState<string | null>(null)
  const [ollamaLoading, setOllamaLoading] = useState(false)
  const [enhancing, setEnhancing] = useState(false)
  const [enhanceError, setEnhanceError] = useState<string | null>(null)

  const onEnhance = async (): Promise<void> => {
    if (!prompt.trim()) return
    setEnhanceError(null)
    setEnhancing(true)
    const response = await window.veraframe.enhancePrompt({
      prompt,
      provider,
      model: model.trim() || undefined,
      ollamaHost: undefined
    })
    setEnhancing(false)
    if (response.ok) {
      setPrompt(response.prompt)
    } else {
      setEnhanceError(response.error)
    }
  }

  const refreshOllamaModels = async (): Promise<void> => {
    setOllamaLoading(true)
    setOllamaError(null)
    const response = await window.veraframe.listOllamaModels(ollamaHost)
    setOllamaLoading(false)
    if (response.ok) {
      setOllamaModels(response.models)
      // If the current model isn't in the new list, default to the first
      // available one (or leave it if list is empty so user sees the error).
      if (response.models.length > 0 && !response.models.includes(model)) {
        setModel(response.models[0])
      }
    } else {
      setOllamaModels([])
      setOllamaError(response.error)
    }
  }

  // Auto-fetch when the user selects Ollama.
  useEffect(() => {
    if (provider === 'ollama') {
      refreshOllamaModels()
    } else {
      setOllamaModels(null)
      setOllamaError(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [provider])
  const [state, setState] = useState<RenderState>({ status: 'idle' })
  const [currentTime, setCurrentTime] = useState(0)
  const videoRef = useRef<HTMLVideoElement | null>(null)

  const onProviderChange = (next: LLMProvider): void => {
    setProvider(next)
    // Switch the model field to the preferred default for the new provider —
    // but only if the user hadn't customized it for the current provider.
    if (model === PROVIDER_DEFAULT_MODEL[provider]) {
      setModel(PROVIDER_DEFAULT_MODEL[next])
    }
  }

  const onRender = async (): Promise<void> => {
    if (mode === 'llm' && !prompt.trim()) return
    setState({ status: 'running' })
    setCurrentTime(0)
    const response = await window.veraframe.render({
      mode,
      prompt: mode === 'llm' ? prompt : undefined,
      provider: mode === 'llm' ? provider : undefined,
      model: mode === 'llm' ? model.trim() || undefined : undefined,
      ollamaHost: undefined
    })
    if (response.ok) {
      setState({
        status: 'success',
        renderId: response.renderId,
        videoUrl: response.videoUrl,
        durationSec: response.durationSec,
        timeline: response.timeline
      })
    } else {
      setState({ status: 'error', message: response.error })
    }
  }

  const [saveNote, setSaveNote] = useState<string | null>(null)
  const onSave = async (renderId: string): Promise<void> => {
    setSaveNote(null)
    const response = await window.veraframe.saveRender(renderId)
    if (response.ok) {
      setSaveNote(`Saved to ${response.path}`)
    } else if (response.error !== 'save canceled') {
      setSaveNote(`Save failed: ${response.error}`)
    }
  }

  const onSeek = (timeSec: number): void => {
    if (videoRef.current) {
      videoRef.current.currentTime = timeSec
    }
  }

  const isRunning = state.status === 'running'
  const disabledSubmit = isRunning || (mode === 'llm' && !prompt.trim())

  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-100">
      <div className="mx-auto flex max-w-4xl flex-col gap-6 p-8">
        <header>
          <h1 className="text-3xl font-bold tracking-tight">Veraframe</h1>
          <p className="mt-1 text-sm text-neutral-400">
            Natural-language animation compiler for Blender
          </p>
        </header>

        <section className="flex flex-col gap-3 rounded-lg border border-neutral-800 bg-neutral-900 p-4">
          <div className="flex items-center gap-4">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="radio"
                name="mode"
                value="mock"
                checked={mode === 'mock'}
                onChange={() => setMode('mock')}
                disabled={isRunning}
              />
              Mock (canned timeline, no LLM)
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="radio"
                name="mode"
                value="llm"
                checked={mode === 'llm'}
                onChange={() => setMode('llm')}
                disabled={isRunning}
              />
              LLM (requires API key)
            </label>
          </div>

          <div className="relative">
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              disabled={mode !== 'llm' || isRunning}
              placeholder={
                mode === 'llm'
                  ? 'Describe a scene, e.g. "the student walks to the center of the lab and smiles"'
                  : 'Mock mode renders a canned timeline; no prompt needed.'
              }
              className="min-h-24 w-full resize-y rounded-md border border-neutral-800 bg-neutral-950 p-3 pr-24 text-sm font-mono placeholder:text-neutral-600 focus:border-neutral-500 focus:outline-none disabled:opacity-50"
            />
            {mode === 'llm' && (
              <button
                type="button"
                onClick={onEnhance}
                disabled={enhancing || isRunning || !prompt.trim()}
                title="Rewrite your prompt using the actual scene/character/spawn names"
                className="absolute right-2 top-2 rounded-md border border-purple-500/60 bg-purple-600/30 px-2 py-1 text-xs font-medium text-purple-200 hover:bg-purple-600/50 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {enhancing ? 'Enhancing…' : '✨ Enhance'}
              </button>
            )}
          </div>
          {enhanceError && (
            <p className="text-xs text-red-400">Enhance failed: {enhanceError}</p>
          )}

          {mode === 'llm' && (
            <div className="flex flex-col gap-2 border-t border-neutral-800 pt-3">
              <div className="grid grid-cols-[6rem_1fr] items-center gap-2">
                <label className="text-xs text-neutral-400">Provider</label>
                <select
                  value={provider}
                  onChange={(e) => onProviderChange(e.target.value as LLMProvider)}
                  disabled={isRunning}
                  className="rounded border border-neutral-800 bg-neutral-950 px-2 py-1 text-sm focus:border-neutral-500 focus:outline-none disabled:opacity-50"
                >
                  {(Object.keys(PROVIDER_LABEL) as LLMProvider[]).map((p) => (
                    <option key={p} value={p}>
                      {PROVIDER_LABEL[p]}
                    </option>
                  ))}
                </select>

                <label className="text-xs text-neutral-400">Model</label>
                {provider === 'ollama' ? (
                  <div className="flex gap-2">
                    <select
                      value={model}
                      onChange={(e) => setModel(e.target.value)}
                      disabled={isRunning || ollamaLoading || !ollamaModels?.length}
                      className="flex-1 rounded border border-neutral-800 bg-neutral-950 px-2 py-1 font-mono text-sm focus:border-neutral-500 focus:outline-none disabled:opacity-50"
                    >
                      {ollamaLoading && <option>Loading…</option>}
                      {!ollamaLoading && ollamaModels?.length === 0 && (
                        <option>No models installed</option>
                      )}
                      {ollamaModels?.map((m) => (
                        <option key={m} value={m}>
                          {m}
                        </option>
                      ))}
                    </select>
                    <button
                      type="button"
                      onClick={refreshOllamaModels}
                      disabled={isRunning || ollamaLoading}
                      className="rounded border border-neutral-700 px-2 py-1 text-xs text-neutral-300 hover:bg-neutral-800 disabled:opacity-50"
                    >
                      ↻
                    </button>
                  </div>
                ) : (
                  <input
                    type="text"
                    value={model}
                    onChange={(e) => setModel(e.target.value)}
                    disabled={isRunning}
                    placeholder={PROVIDER_DEFAULT_MODEL[provider]}
                    className="rounded border border-neutral-800 bg-neutral-950 px-2 py-1 font-mono text-sm focus:border-neutral-500 focus:outline-none disabled:opacity-50"
                  />
                )}

              </div>
              {provider === 'ollama' && ollamaError && (
                <p className="text-xs text-red-400">{ollamaError}</p>
              )}
              {provider === 'ollama' && !ollamaError && ollamaModels?.length === 0 && (
                <p className="text-xs text-neutral-500">
                  Reached Ollama, but no models installed. Run{' '}
                  <code className="font-mono">ollama pull llama3.1</code> in a terminal.
                </p>
              )}
              {provider === 'ollama' && !ollamaError && (ollamaModels?.length ?? 0) > 0 && (
                <p className="text-xs text-neutral-500">
                  Local Ollama, no API key needed. {ollamaModels?.length} model
                  {ollamaModels?.length === 1 ? '' : 's'} available.
                </p>
              )}
              {provider !== 'ollama' && (
                <p className="text-xs text-neutral-500">
                  Set the matching <code className="font-mono">{providerKeyEnv(provider)}</code> env
                  var in the shell that launched Electron.
                </p>
              )}
            </div>
          )}

          <button
            type="button"
            onClick={onRender}
            disabled={disabledSubmit}
            className="self-start rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-500 disabled:cursor-not-allowed disabled:bg-neutral-700"
          >
            {isRunning ? 'Rendering…' : 'Render'}
          </button>
        </section>

        <section className="flex flex-col gap-2">
          {state.status === 'idle' && (
            <p className="text-sm text-neutral-500">No render yet.</p>
          )}
          {state.status === 'running' && (
            <p className="text-sm text-neutral-400">
              Rendering — this can take a minute or two on the first call (Blender startup).
            </p>
          )}
          {state.status === 'error' && (
            <p className="text-sm text-red-400">
              <span className="font-semibold">Render failed:</span> {state.message}
            </p>
          )}
          {state.status === 'success' && (
            <>
              <div className="flex items-center justify-between">
                <p className="text-sm text-neutral-400">
                  Rendered {state.durationSec.toFixed(1)}s
                </p>
                <button
                  type="button"
                  onClick={() => onSave(state.renderId)}
                  className="rounded-md border border-neutral-700 px-3 py-1 text-xs font-medium text-neutral-200 hover:bg-neutral-800"
                >
                  Save Video…
                </button>
              </div>
              {saveNote && (
                <p className="text-xs text-neutral-500 break-all">{saveNote}</p>
              )}
              <video
                ref={videoRef}
                key={state.videoUrl}
                src={state.videoUrl}
                controls
                autoPlay
                loop
                onTimeUpdate={(e) => setCurrentTime(e.currentTarget.currentTime)}
                className="w-full rounded-md border border-neutral-800"
              />
              <TimelinePanel
                timeline={state.timeline}
                currentTimeSec={currentTime}
                durationSec={state.durationSec}
                onSeek={onSeek}
              />
            </>
          )}
        </section>
      </div>
    </div>
  )
}

function providerKeyEnv(provider: LLMProvider): string {
  switch (provider) {
    case 'openai':
      return 'OPENAI_API_KEY'
    case 'anthropic':
      return 'ANTHROPIC_API_KEY'
    case 'gemini':
      return 'GEMINI_API_KEY'
    case 'ollama':
      return ''
  }
}

export default App
