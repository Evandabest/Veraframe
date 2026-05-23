/**
 * Modal for editing or adding a single action block.
 *
 * Two phases:
 *   1. PROMPT — user types what they want; "Generate" calls the LLM.
 *   2. PREVIEW — shows the generated Action JSON next to the original (if
 *      any). User chooses Accept (triggers re-render) or Reject (discards).
 *
 * The component itself is dumb — App owns the state and the LLM call. We
 * receive the original action (or null for an "add" flow), the pending new
 * action (filled in by App after the LLM returns), and three callbacks.
 */

import { useEffect, useRef, useState } from 'react'

interface ActionLike {
  id: string
  type: string
  start: number
  end: number
  [key: string]: unknown
}

export interface ActionEditorProps {
  open: boolean
  original: ActionLike | null
  /** Lane (character handle) the action belongs to. Shown for context. */
  laneId: string
  /** Start time the new action will use (fixed by the lane). */
  startSec: number
  /** Locked end time (edit flow). Null = LLM chooses duration. */
  endSec: number | null
  /** Filled in by App after the LLM call returns. */
  pendingAction: ActionLike | null
  /** True while the LLM call is in-flight. */
  generating: boolean
  /** Surfaces LLM/IPC errors. */
  error: string | null
  onGenerate: (prompt: string) => void
  onAccept: () => void
  onReject: () => void
  onClose: () => void
  /** Optional: rewrite the prompt to use registry names. Mirrors the main
   *  Enhance button. Returns the rewritten text or throws/null on failure. */
  onEnhance?: (prompt: string) => Promise<string | null>
  /** Seed value for the prompt textarea. Used by the verb palette to prefill
   *  the verb's natural-language hint (e.g. "nod"). Re-applied each time
   *  the editor opens. */
  initialPrompt?: string
}

export function ActionEditor(props: ActionEditorProps): React.JSX.Element | null {
  const {
    open,
    original,
    laneId,
    startSec,
    endSec,
    pendingAction,
    generating,
    error,
    onGenerate,
    onAccept,
    onReject,
    onClose,
    onEnhance,
    initialPrompt
  } = props

  const [prompt, setPrompt] = useState(initialPrompt ?? '')
  const [enhancing, setEnhancing] = useState(false)
  const [enhanceError, setEnhanceError] = useState<string | null>(null)
  // Pending enhancement, shown in a review panel before the user
  // accepts or rejects it (mirrors the main scene-prompt Enhance flow).
  const [pendingEnhanced, setPendingEnhanced] = useState<string | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)

  // Reset the prompt and focus the textarea each time the modal opens for a
  // new target. When the palette drop seeded a prompt we keep it instead of
  // clearing — the cursor lands at the end so the user can finish the line.
  useEffect(() => {
    if (open) {
      setPrompt(initialPrompt ?? '')
      setEnhanceError(null)
      setPendingEnhanced(null)
      setTimeout(() => {
        const ta = textareaRef.current
        if (!ta) return
        ta.focus()
        ta.setSelectionRange(ta.value.length, ta.value.length)
      }, 30)
    }
  }, [open, original?.id, laneId, initialPrompt])

  if (!open) return null

  const submitDisabled = !prompt.trim() || generating || pendingAction !== null
  const flowLabel = original ? 'Edit action' : 'Add action'
  const timeLabel =
    endSec !== null
      ? `${startSec.toFixed(1)}s–${endSec.toFixed(1)}s`
      : `from ${startSec.toFixed(1)}s · duration set by LLM`

  const onEnhanceClick = async (): Promise<void> => {
    if (!onEnhance || !prompt.trim() || enhancing) return
    setEnhanceError(null)
    setEnhancing(true)
    setPendingEnhanced(null)
    try {
      const rewritten = await onEnhance(prompt)
      if (rewritten && rewritten.trim()) {
        setPendingEnhanced(rewritten.trim())
      }
    } catch (e) {
      setEnhanceError((e as Error).message)
    } finally {
      setEnhancing(false)
    }
  }

  const onAcceptEnhanced = (): void => {
    if (pendingEnhanced) setPrompt(pendingEnhanced)
    setPendingEnhanced(null)
  }
  const onRejectEnhanced = (): void => {
    setPendingEnhanced(null)
  }

  return (
    <div
      onClick={onClose}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="flex w-full max-w-lg flex-col gap-4 rounded-xl border border-neutral-700 bg-neutral-900 p-5 shadow-xl"
      >
        <header className="flex items-baseline justify-between">
          <h3 className="text-base font-semibold text-neutral-100">{flowLabel}</h3>
          <span className="font-mono text-xs text-neutral-500">
            {laneId} · {timeLabel}
          </span>
        </header>

        {original && (
          <div className="rounded-md border border-neutral-800 bg-neutral-950 p-2 text-xs">
            <p className="mb-1 text-[11px] uppercase tracking-wide text-neutral-500">
              Currently
            </p>
            <pre className="overflow-x-auto font-mono text-neutral-300">
              {JSON.stringify(original, null, 2)}
            </pre>
          </div>
        )}

        <div className="flex flex-col gap-1">
          <label className="text-xs text-neutral-400">
            What should the character do during this slot?
          </label>
          <div className="relative">
            <textarea
              ref={textareaRef}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              disabled={generating || enhancing}
              placeholder='e.g. "smile while looking at the robot" or "walk to the door"'
              className="min-h-24 w-full resize-y rounded-md border border-neutral-800 bg-neutral-950 p-3 pr-24 text-sm font-mono placeholder:text-neutral-600 focus:border-neutral-500 focus:outline-none disabled:opacity-50"
            />
            {onEnhance && (
              <button
                type="button"
                onClick={onEnhanceClick}
                disabled={enhancing || generating || !prompt.trim()}
                title="Rewrite the prompt using registry asset names"
                className="absolute right-2 top-2 rounded-md border border-purple-500/60 bg-purple-600/30 px-2 py-1 text-xs font-medium text-purple-200 hover:bg-purple-600/50 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {enhancing ? 'Enhancing…' : '✨ Enhance'}
              </button>
            )}
          </div>
          {enhanceError && (
            <p className="text-xs text-red-400">Enhance failed: {enhanceError}</p>
          )}
          {pendingEnhanced && (
            <div className="rounded-md border border-purple-500/60 bg-purple-500/10 p-2 text-xs">
              <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-purple-200">
                Enhanced rewrite
              </p>
              <pre className="whitespace-pre-wrap font-mono text-purple-50">
                {pendingEnhanced}
              </pre>
              <div className="mt-2 flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={onRejectEnhanced}
                  className="rounded border border-neutral-700 px-2 py-0.5 text-[11px] text-neutral-200 hover:bg-neutral-800"
                >
                  Reject
                </button>
                <button
                  type="button"
                  onClick={onAcceptEnhanced}
                  className="rounded bg-purple-600 px-2 py-0.5 text-[11px] font-semibold text-white hover:bg-purple-500"
                >
                  Accept rewrite
                </button>
              </div>
            </div>
          )}
        </div>

        {error && <p className="text-xs text-red-400">{error}</p>}

        {pendingAction && (
          <div className="rounded-md border border-emerald-500/60 bg-emerald-500/10 p-3">
            <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-emerald-300">
              Proposed
            </p>
            <pre className="overflow-x-auto font-mono text-xs text-emerald-50">
              {JSON.stringify(pendingAction, null, 2)}
            </pre>
            <p className="mt-2 text-[11px] text-emerald-200/70">
              The new block is highlighted in green on the timeline behind this dialog.
              Accept to re-render the video; Reject to keep the original.
            </p>
          </div>
        )}

        <footer className="flex items-center justify-end gap-2">
          {pendingAction ? (
            <>
              <button
                type="button"
                onClick={onReject}
                className="rounded-md border border-neutral-700 px-3 py-1.5 text-sm text-neutral-200 hover:bg-neutral-800"
              >
                Reject
              </button>
              <button
                type="button"
                onClick={onAccept}
                className="rounded-md bg-emerald-600 px-4 py-1.5 text-sm font-semibold text-white hover:bg-emerald-500"
              >
                Accept &amp; re-render
              </button>
            </>
          ) : (
            <>
              <button
                type="button"
                onClick={onClose}
                disabled={generating}
                className="rounded-md border border-neutral-700 px-3 py-1.5 text-sm text-neutral-200 hover:bg-neutral-800 disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => onGenerate(prompt)}
                disabled={submitDisabled}
                className="rounded-md bg-blue-600 px-4 py-1.5 text-sm font-semibold text-white hover:bg-blue-500 disabled:cursor-not-allowed disabled:bg-neutral-700"
              >
                {generating ? 'Generating…' : 'Generate'}
              </button>
            </>
          )}
        </footer>
      </div>
    </div>
  )
}
