/**
 * Floating prompt panel for natural-language range edits.
 *
 * Shows up when the user shift+drags a window on the timeline. The user
 * types what should happen in that window; the panel calls the LLM and
 * the parent (App.tsx) merges the resulting action list into the timeline,
 * showing a side-by-side preview before committing the render.
 */

import { useEffect, useRef, useState } from 'react'

export interface RangeEditPanelProps {
  /** Active selection [start, end]. Null hides the panel. */
  range: { start: number; end: number } | null
  /** True while the LLM call is in flight. */
  generating: boolean
  /** Surfaces LLM/IPC errors. */
  error: string | null
  /** Cancel button — clears the selection and closes the panel. */
  onCancel: () => void
  /** Submit the prompt; the parent makes the LLM call and previews the
   *  result. The pending preview UI lives in App next to the timeline. */
  onSubmit: (prompt: string) => void
}

export function RangeEditPanel({
  range,
  generating,
  error,
  onCancel,
  onSubmit
}: RangeEditPanelProps): React.JSX.Element | null {
  const [prompt, setPrompt] = useState('')
  const inputRef = useRef<HTMLTextAreaElement | null>(null)

  // Reset the prompt when a new range is selected.
  useEffect(() => {
    if (range) {
      setPrompt('')
      setTimeout(() => inputRef.current?.focus(), 30)
    }
  }, [range?.start, range?.end])

  if (!range) return null
  const submitDisabled = !prompt.trim() || generating

  return (
    <div className="flex flex-col gap-2 rounded-lg border border-blue-500/60 bg-blue-500/10 p-3">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold text-blue-100">
          Edit range {range.start.toFixed(1)}s – {range.end.toFixed(1)}s
        </p>
        <button
          type="button"
          onClick={onCancel}
          disabled={generating}
          className="rounded border border-neutral-700 px-2 py-0.5 text-[11px] text-neutral-200 hover:bg-neutral-800 disabled:opacity-50"
        >
          Clear
        </button>
      </div>
      <p className="text-[11px] text-blue-100/80">
        Describe what should happen in this window. Existing actions inside
        the window are replaced; everything outside is untouched. Tip:
        shift+drag elsewhere on the timeline to pick a different window.
      </p>
      <textarea
        ref={inputRef}
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        disabled={generating}
        placeholder='e.g. "alice paces nervously between the desks"'
        className="min-h-16 w-full resize-y rounded-md border border-neutral-800 bg-neutral-950 p-2 text-sm font-mono placeholder:text-neutral-600 focus:border-neutral-500 focus:outline-none disabled:opacity-50"
        onKeyDown={(e) => {
          if (e.key === 'Enter' && (e.metaKey || e.ctrlKey) && !submitDisabled) {
            onSubmit(prompt)
          }
          if (e.key === 'Escape' && !generating) onCancel()
        }}
      />
      {error && <p className="text-xs text-red-300">{error}</p>}
      <div className="flex items-center justify-end gap-2">
        <button
          type="button"
          onClick={() => onSubmit(prompt)}
          disabled={submitDisabled}
          title="⌘/Ctrl+Enter to submit"
          className="rounded-md bg-blue-600 px-3 py-1 text-xs font-semibold text-white hover:bg-blue-500 disabled:cursor-not-allowed disabled:bg-neutral-700"
        >
          {generating ? 'Generating…' : 'Rewrite range'}
        </button>
      </div>
    </div>
  )
}
