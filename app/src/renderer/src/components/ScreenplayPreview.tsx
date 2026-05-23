/**
 * Editable preview of an LLM-proposed screenplay breakdown (Step 40).
 *
 * Each row corresponds to one shot-level beat the breakdown subprocess
 * inferred from the screenplay text. The user can:
 *   - Edit the prompt for any row
 *   - Adjust start / end times
 *   - Delete a row
 *   - Hit "Approve & render" to feed the segments into the Script-mode
 *     render path (compileScriptToPrompt does the rest)
 *   - Hit "Re-run breakdown" to ask the LLM again with the same text
 */

import { useEffect, useState } from 'react'

import type { ScriptSegment } from '../script'

export interface ScreenplayPreviewProps {
  /** Segments as proposed by the LLM. Set to null to hide the panel. */
  proposed: ScriptSegment[] | null
  /** True while the breakdown subprocess is running. */
  generating: boolean
  error: string | null
  /** Re-run the breakdown with the same input. */
  onRebreak: () => void
  /** Hand the (possibly-edited) segment list to the render path. */
  onApprove: (segments: ScriptSegment[]) => void
  /** Clear the preview without rendering. */
  onCancel: () => void
}

export function ScreenplayPreview({
  proposed,
  generating,
  error,
  onRebreak,
  onApprove,
  onCancel
}: ScreenplayPreviewProps): React.JSX.Element | null {
  const [rows, setRows] = useState<ScriptSegment[]>([])

  // Reseed the editable rows whenever the LLM returns a fresh breakdown.
  useEffect(() => {
    if (proposed) setRows(proposed.map((s) => ({ ...s })))
  }, [proposed])

  if (!proposed && !generating && !error) return null

  const updateRow = (i: number, patch: Partial<ScriptSegment>): void => {
    setRows((prev) => prev.map((r, idx) => (idx === i ? { ...r, ...patch } : r)))
  }
  const deleteRow = (i: number): void => {
    setRows((prev) => prev.filter((_, idx) => idx !== i))
  }

  return (
    <div className="flex flex-col gap-2 rounded-lg border border-purple-500/50 bg-purple-500/10 p-3">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold text-purple-100">
          Screenplay breakdown {rows.length > 0 && `· ${rows.length} beat${rows.length === 1 ? '' : 's'}`}
        </p>
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={onRebreak}
            disabled={generating}
            title="Ask the LLM to re-break the same text"
            className="rounded border border-neutral-700 px-2 py-0.5 text-[11px] text-neutral-200 hover:bg-neutral-800 disabled:opacity-50"
          >
            ↻ Re-run
          </button>
          <button
            type="button"
            onClick={onCancel}
            disabled={generating}
            className="rounded border border-neutral-700 px-2 py-0.5 text-[11px] text-neutral-200 hover:bg-neutral-800 disabled:opacity-50"
          >
            Cancel
          </button>
        </div>
      </div>

      {generating && (
        <p className="text-[11px] italic text-purple-200/80">Breaking down screenplay…</p>
      )}
      {error && <p className="text-xs text-red-300">{error}</p>}

      {rows.length > 0 && (
        <ul className="flex flex-col gap-1">
          {rows.map((r, i) => (
            <li
              key={i}
              className="grid grid-cols-[60px_60px_1fr_28px] items-center gap-2 rounded border border-neutral-800 bg-neutral-950/60 px-2 py-1"
            >
              <input
                type="number"
                step={0.1}
                min={0}
                value={r.start}
                onChange={(e) => updateRow(i, { start: Number(e.target.value) })}
                disabled={generating}
                title="Start (s)"
                className="rounded border border-neutral-800 bg-neutral-900 px-1 py-0.5 text-[11px] focus:border-neutral-500 focus:outline-none"
              />
              <input
                type="number"
                step={0.1}
                min={0}
                value={r.end ?? 0}
                onChange={(e) => updateRow(i, { end: Number(e.target.value) })}
                disabled={generating}
                title="End (s)"
                className="rounded border border-neutral-800 bg-neutral-900 px-1 py-0.5 text-[11px] focus:border-neutral-500 focus:outline-none"
              />
              <input
                type="text"
                value={r.prompt}
                onChange={(e) => updateRow(i, { prompt: e.target.value })}
                disabled={generating}
                className="rounded border border-neutral-800 bg-neutral-900 px-1.5 py-0.5 text-xs focus:border-neutral-500 focus:outline-none"
              />
              <button
                type="button"
                onClick={() => deleteRow(i)}
                disabled={generating}
                title="Delete this beat"
                className="rounded border border-red-500/60 bg-red-500/10 px-1.5 py-0.5 text-[10px] text-red-200 hover:bg-red-500/25 disabled:opacity-40"
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}

      {rows.length > 0 && (
        <div className="flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={() => onApprove(rows)}
            disabled={generating || rows.length === 0}
            className="rounded-md bg-purple-600 px-3 py-1 text-xs font-semibold text-white hover:bg-purple-500 disabled:cursor-not-allowed disabled:bg-neutral-700"
          >
            Approve &amp; render
          </button>
        </div>
      )}
    </div>
  )
}
