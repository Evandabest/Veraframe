import { useState } from 'react'

type RenderState =
  | { status: 'idle' }
  | { status: 'running' }
  | { status: 'success'; renderId: string; videoUrl: string; durationSec: number }
  | { status: 'error'; message: string }

function App(): React.JSX.Element {
  const [mode, setMode] = useState<'mock' | 'llm'>('mock')
  const [prompt, setPrompt] = useState('')
  const [state, setState] = useState<RenderState>({ status: 'idle' })

  const onRender = async (): Promise<void> => {
    if (mode === 'llm' && !prompt.trim()) return
    setState({ status: 'running' })
    const response = await window.veraframe.render({
      mode,
      prompt: mode === 'llm' ? prompt : undefined
    })
    if (response.ok) {
      setState({
        status: 'success',
        renderId: response.renderId,
        videoUrl: response.videoUrl,
        durationSec: response.durationSec
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

  const isRunning = state.status === 'running'
  const disabledSubmit = isRunning || (mode === 'llm' && !prompt.trim())

  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-100">
      <div className="mx-auto flex max-w-3xl flex-col gap-6 p-8">
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

          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            disabled={mode !== 'llm' || isRunning}
            placeholder={
              mode === 'llm'
                ? 'Describe a scene, e.g. "the student walks to the center of the lab and smiles"'
                : 'Mock mode renders a canned timeline; no prompt needed.'
            }
            className="min-h-24 w-full resize-y rounded-md border border-neutral-800 bg-neutral-950 p-3 text-sm font-mono placeholder:text-neutral-600 focus:border-neutral-500 focus:outline-none disabled:opacity-50"
          />

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
                key={state.videoUrl}
                src={state.videoUrl}
                controls
                autoPlay
                loop
                className="w-full rounded-md border border-neutral-800"
              />
            </>
          )}
        </section>
      </div>
    </div>
  )
}

export default App
