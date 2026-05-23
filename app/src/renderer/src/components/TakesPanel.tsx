/**
 * Non-destructive branch board.
 *
 * Lists every saved take with its name, capture time, and an "active" badge
 * when it's the one currently loaded. Each row offers Restore / Rename /
 * Delete. The active take auto-rolls forward in App when the user edits or
 * re-renders so subsequent saves capture the latest state.
 */

import { useState } from 'react'

import type { Take } from '../takes'

export interface TakesPanelProps {
  takes: Take[]
  activeTakeId: string | null
  /** Disabled when no rendered timeline exists. */
  canSave: boolean
  onSave: () => void
  onRestore: (id: string) => void
  onRename: (id: string, name: string) => void
  onDelete: (id: string) => void
}

export function TakesPanel({
  takes,
  activeTakeId,
  canSave,
  onSave,
  onRestore,
  onRename,
  onDelete
}: TakesPanelProps): React.JSX.Element {
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-neutral-800 bg-neutral-900 p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-neutral-200">Takes</h2>
        <button
          type="button"
          onClick={onSave}
          disabled={!canSave}
          title={
            canSave
              ? 'Snapshot the current timeline + render as a new take'
              : 'Render once before saving a take'
          }
          className="rounded-md border border-emerald-500 bg-emerald-500/15 px-2 py-0.5 text-[11px] font-medium text-emerald-200 hover:bg-emerald-500/30 disabled:opacity-50"
        >
          + Save as take
        </button>
      </div>

      {takes.length === 0 ? (
        <p className="text-[11px] text-neutral-500">
          No takes saved. Each take captures the timeline and render at that
          moment so you can iterate without losing earlier versions.
        </p>
      ) : (
        <ul className="flex flex-col gap-1">
          {takes.map((t) => (
            <TakeRow
              key={t.id}
              take={t}
              active={t.id === activeTakeId}
              onRestore={() => onRestore(t.id)}
              onRename={(name) => onRename(t.id, name)}
              onDelete={() => onDelete(t.id)}
            />
          ))}
        </ul>
      )}
    </div>
  )
}

interface TakeRowProps {
  take: Take
  active: boolean
  onRestore: () => void
  onRename: (name: string) => void
  onDelete: () => void
}

function TakeRow({ take, active, onRestore, onRename, onDelete }: TakeRowProps): React.JSX.Element {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(take.name)

  const commitRename = (): void => {
    if (draft.trim() && draft.trim() !== take.name) onRename(draft)
    setEditing(false)
  }

  const savedAt = new Date(take.savedAt)
  const savedLabel = `${savedAt.toLocaleDateString()} ${savedAt.toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit'
  })}`

  return (
    <li
      className={`flex items-center justify-between gap-2 rounded border px-2 py-1.5 text-xs ${
        active
          ? 'border-blue-500/60 bg-blue-500/10'
          : 'border-neutral-800 bg-neutral-950/60'
      }`}
    >
      <div className="flex min-w-0 flex-1 flex-col">
        {editing ? (
          <input
            autoFocus
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={commitRename}
            onKeyDown={(e) => {
              if (e.key === 'Enter') commitRename()
              if (e.key === 'Escape') {
                setDraft(take.name)
                setEditing(false)
              }
            }}
            className="rounded border border-neutral-700 bg-neutral-900 px-1 py-0.5 text-xs text-neutral-100 focus:border-neutral-500 focus:outline-none"
          />
        ) : (
          <button
            type="button"
            onClick={() => {
              setDraft(take.name)
              setEditing(true)
            }}
            title="Click to rename"
            className="truncate text-left font-medium text-neutral-100 hover:underline"
          >
            {take.name}
            {active && (
              <span className="ml-1 text-[10px] font-normal text-blue-300">· active</span>
            )}
          </button>
        )}
        <span className="truncate text-[10px] text-neutral-500" title={take.prompt}>
          {savedLabel} · {take.durationSec.toFixed(1)}s
          {take.prompt && <> · {take.prompt}</>}
        </span>
      </div>

      <div className="flex flex-shrink-0 items-center gap-1">
        <button
          type="button"
          onClick={onRestore}
          disabled={active}
          title="Switch the editor to this take"
          className="rounded border border-neutral-700 px-1.5 py-0.5 text-[10px] text-neutral-200 hover:bg-neutral-800 disabled:opacity-40"
        >
          Restore
        </button>
        <button
          type="button"
          onClick={() => {
            if (window.confirm(`Delete take "${take.name}"? The render itself is unaffected.`)) {
              onDelete()
            }
          }}
          title="Delete this take"
          className="rounded border border-red-500/60 bg-red-500/10 px-1.5 py-0.5 text-[10px] text-red-200 hover:bg-red-500/25"
        >
          ×
        </button>
      </div>
    </li>
  )
}
