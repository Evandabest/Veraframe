/**
 * Upload modal for a single user-supplied motion clip (Step 51, Option C).
 *
 * Captures an id, display name, optional description, and a path to the
 * source FBX (or BVH). The main process copies the file into the user's
 * assets dir under motions/<id>/clip.fbx and writes a motion.json
 * manifest. The clip then appears in the Library and in the LLM's
 * "Available motion clips" section so it can pick `play_clip(clip=<id>)`.
 */

import { useState } from 'react'

export interface AddMotionClipModalProps {
  open: boolean
  onClose: () => void
  onSaved: () => void
}

export function AddMotionClipModal({
  open,
  onClose,
  onSaved
}: AddMotionClipModalProps): React.JSX.Element | null {
  const [id, setId] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [description, setDescription] = useState('')
  const [sourcePath, setSourcePath] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (!open) return null

  const reset = (): void => {
    setId('')
    setDisplayName('')
    setDescription('')
    setSourcePath('')
    setSubmitting(false)
    setError(null)
  }

  const onPick = async (): Promise<void> => {
    const r = await window.veraframe.pickAssetFile('character')
    if (r.ok) setSourcePath(r.filePath)
  }

  const onSave = async (): Promise<void> => {
    if (!id.trim() || !displayName.trim() || !sourcePath) {
      setError('id, display name, and a source FBX are all required.')
      return
    }
    setError(null)
    setSubmitting(true)
    const response = await window.veraframe.addMotion({
      sourcePath,
      id: id.trim(),
      displayName: displayName.trim(),
      description: description.trim() || undefined
    })
    setSubmitting(false)
    if (response.ok) {
      reset()
      onSaved()
    } else {
      setError(response.error)
    }
  }

  return (
    <div
      onClick={() => {
        reset()
        onClose()
      }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="flex w-full max-w-lg flex-col gap-4 rounded-xl border border-neutral-700 bg-neutral-900 p-5 shadow-xl"
      >
        <header>
          <h3 className="text-base font-semibold text-neutral-100">Add motion clip</h3>
          <p className="mt-1 text-xs text-neutral-400">
            Drop in any Mixamo-rigged FBX (or any FBX whose embedded animation
            targets a Mixamo-style skeleton). The clip becomes available to
            the <code className="font-mono">play_clip</code> action.
          </p>
        </header>

        <div className="grid grid-cols-2 gap-3">
          <div className="flex flex-col gap-1">
            <label className="text-xs text-neutral-400">
              ID <span className="text-neutral-500">(alphanum + _)</span>
            </label>
            <input
              type="text"
              value={id}
              onChange={(e) => setId(e.target.value)}
              placeholder="kick"
              className="rounded border border-neutral-800 bg-neutral-950 px-2 py-1 font-mono text-sm focus:border-neutral-500 focus:outline-none"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-neutral-400">Display name</label>
            <input
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="Spinning kick"
              className="rounded border border-neutral-800 bg-neutral-950 px-2 py-1 text-sm focus:border-neutral-500 focus:outline-none"
            />
          </div>
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-xs text-neutral-400">
            Description <span className="text-neutral-500">(helps the LLM choose this clip)</span>
          </label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="An aggressive martial-arts spinning kick. ~1.5s long."
            className="min-h-16 w-full resize-y rounded border border-neutral-800 bg-neutral-950 px-2 py-1 text-sm focus:border-neutral-500 focus:outline-none"
          />
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-xs text-neutral-400">Source FBX</label>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onPick}
              className="rounded border border-neutral-700 bg-neutral-950 px-3 py-1 text-xs text-neutral-200 hover:border-neutral-500"
            >
              {sourcePath ? 'Pick a different file…' : 'Pick a file…'}
            </button>
            <span className="flex-1 truncate font-mono text-[11px] text-neutral-500" title={sourcePath}>
              {sourcePath || '(none)'}
            </span>
          </div>
        </div>

        {error && <p className="text-xs text-red-400">{error}</p>}

        <footer className="flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={() => {
              reset()
              onClose()
            }}
            disabled={submitting}
            className="rounded-md border border-neutral-700 px-3 py-1.5 text-sm text-neutral-200 hover:bg-neutral-800 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onSave}
            disabled={submitting}
            className="rounded-md bg-emerald-600 px-4 py-1.5 text-sm font-semibold text-white hover:bg-emerald-500 disabled:cursor-not-allowed disabled:bg-neutral-700"
          >
            {submitting ? 'Saving…' : 'Add clip'}
          </button>
        </footer>
      </div>
    </div>
  )
}
