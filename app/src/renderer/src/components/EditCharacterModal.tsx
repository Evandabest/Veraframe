/**
 * Per-file edit modal for a user-uploaded character.
 *
 * Shows the current display name + the three FBX file paths. Each file has
 * its own "Replace…" button — unchanged files stay as they are. Save POSTs
 * only the changed fields to `updateCharacter`.
 */

import { useEffect, useState } from 'react'

export interface EditCharacterModalProps {
  open: boolean
  /** The character being edited. Identified by id. */
  characterId: string
  initialDisplayName: string
  /** Profile fields surfaced from the registry summary. Empty string when unset. */
  initialDescription?: string
  initialDefaultEmotion?: string
  initialVoice?: string
  /** Paths shown in the UI for context — read-only. They live under the
   *  user-data folder and don't change unless the user replaces a file. */
  meshPath: string
  idlePath: string
  walkPath: string
  onClose: () => void
  onSaved: () => void
}

const EMOTION_VALUES = ['neutral', 'joy', 'angry', 'sorrow', 'fun'] as const

export function EditCharacterModal(props: EditCharacterModalProps): React.JSX.Element | null {
  const {
    open,
    characterId,
    initialDisplayName,
    initialDescription = '',
    initialDefaultEmotion = '',
    initialVoice = '',
    meshPath,
    idlePath,
    walkPath
  } = props

  const [displayName, setDisplayName] = useState(initialDisplayName)
  const [description, setDescription] = useState(initialDescription)
  const [defaultEmotion, setDefaultEmotion] = useState(initialDefaultEmotion)
  const [voice, setVoice] = useState(initialVoice)
  const [newMesh, setNewMesh] = useState<string | null>(null)
  const [newIdle, setNewIdle] = useState<string | null>(null)
  const [newWalk, setNewWalk] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setDisplayName(initialDisplayName)
    setDescription(initialDescription)
    setDefaultEmotion(initialDefaultEmotion)
    setVoice(initialVoice)
    setNewMesh(null)
    setNewIdle(null)
    setNewWalk(null)
    setError(null)
    setSubmitting(false)
  }, [
    open,
    initialDisplayName,
    initialDescription,
    initialDefaultEmotion,
    initialVoice,
    characterId
  ])

  if (!open) return null

  const pickFbx = async (setter: (p: string) => void): Promise<void> => {
    const result = await window.veraframe.pickAssetFile('character')
    if (result.ok) setter(result.filePath)
  }

  const hasChange =
    newMesh !== null ||
    newIdle !== null ||
    newWalk !== null ||
    displayName !== initialDisplayName ||
    description !== initialDescription ||
    defaultEmotion !== initialDefaultEmotion ||
    voice !== initialVoice

  const onSave = async (): Promise<void> => {
    setError(null)
    setSubmitting(true)
    const response = await window.veraframe.updateCharacter({
      id: characterId,
      meshPath: newMesh,
      idlePath: newIdle,
      walkPath: newWalk,
      displayName: displayName !== initialDisplayName ? displayName : null,
      description: description !== initialDescription ? description : null,
      defaultEmotion:
        defaultEmotion !== initialDefaultEmotion ? defaultEmotion : null,
      voice: voice !== initialVoice ? voice : null
    })
    setSubmitting(false)
    if (response.ok) {
      props.onSaved()
    } else {
      setError(response.error)
    }
  }

  return (
    <div
      onClick={props.onClose}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="flex w-full max-w-lg flex-col gap-4 rounded-xl border border-neutral-700 bg-neutral-900 p-5 shadow-xl"
      >
        <header>
          <h3 className="text-base font-semibold text-neutral-100">
            Edit character · <span className="font-mono">{characterId}</span>
          </h3>
          <p className="mt-1 text-xs text-neutral-400">
            Replace the mesh or animation clips without re-uploading the whole
            character. Unchanged files stay as they are.
          </p>
        </header>

        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1">
            <label className="text-xs text-neutral-400">Display name</label>
            <input
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              className="w-full rounded border border-neutral-800 bg-neutral-950 px-2 py-1 text-sm focus:border-neutral-500 focus:outline-none"
            />
          </div>

          <div className="flex flex-col gap-1">
            <label className="text-xs text-neutral-400">
              Description
              <span className="ml-1 text-neutral-500">
                (folded into the LLM prompt so the model can reason about the character)
              </span>
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="e.g. anxious lab student, hesitant body language"
              className="min-h-16 w-full resize-y rounded border border-neutral-800 bg-neutral-950 px-2 py-1 text-sm focus:border-neutral-500 focus:outline-none"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1">
              <label className="text-xs text-neutral-400">Default emotion</label>
              <select
                value={defaultEmotion}
                onChange={(e) => setDefaultEmotion(e.target.value)}
                className="rounded border border-neutral-800 bg-neutral-950 px-2 py-1 text-sm focus:border-neutral-500 focus:outline-none"
              >
                <option value="">— none —</option>
                {EMOTION_VALUES.map((e) => (
                  <option key={e} value={e}>
                    {e}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs text-neutral-400">
                TTS voice
                <span className="ml-1 text-neutral-500" title="Provider-specific. Example: en-US-AriaNeural (Edge TTS), alloy (OpenAI).">
                  (?)
                </span>
              </label>
              <input
                type="text"
                value={voice}
                onChange={(e) => setVoice(e.target.value)}
                placeholder="e.g. en-US-AriaNeural"
                className="rounded border border-neutral-800 bg-neutral-950 px-2 py-1 text-sm font-mono focus:border-neutral-500 focus:outline-none"
              />
            </div>
          </div>

          <SwapRow
            label="Mesh (.fbx)"
            current={meshPath}
            pending={newMesh}
            onPick={() => pickFbx(setNewMesh)}
            onClear={() => setNewMesh(null)}
          />
          <SwapRow
            label="Idle animation (.fbx)"
            current={idlePath}
            pending={newIdle}
            onPick={() => pickFbx(setNewIdle)}
            onClear={() => setNewIdle(null)}
          />
          <SwapRow
            label="Walk animation (.fbx)"
            current={walkPath}
            pending={newWalk}
            onPick={() => pickFbx(setNewWalk)}
            onClear={() => setNewWalk(null)}
          />
        </div>

        {error && <p className="text-xs text-red-400">{error}</p>}

        <footer className="flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={props.onClose}
            disabled={submitting}
            className="rounded-md border border-neutral-700 px-3 py-1.5 text-sm text-neutral-200 hover:bg-neutral-800 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onSave}
            disabled={!hasChange || submitting}
            className="rounded-md bg-emerald-600 px-4 py-1.5 text-sm font-semibold text-white hover:bg-emerald-500 disabled:cursor-not-allowed disabled:bg-neutral-700"
          >
            {submitting ? 'Saving…' : 'Save changes'}
          </button>
        </footer>
      </div>
    </div>
  )
}

function SwapRow({
  label,
  current,
  pending,
  onPick,
  onClear
}: {
  label: string
  current: string
  pending: string | null
  onPick: () => void
  onClear: () => void
}): React.JSX.Element {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-xs text-neutral-400">{label}</label>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onPick}
          className="rounded border border-neutral-700 bg-neutral-950 px-3 py-1 text-xs text-neutral-200 hover:border-neutral-500"
        >
          {pending ? 'Pick again…' : 'Replace…'}
        </button>
        {pending && (
          <button
            type="button"
            onClick={onClear}
            className="rounded border border-neutral-700 px-2 py-1 text-xs text-neutral-400 hover:text-neutral-200"
          >
            keep current
          </button>
        )}
        <span
          className="flex-1 truncate font-mono text-[11px] text-neutral-500"
          title={pending ?? current}
        >
          {pending ? <span className="text-emerald-300">→ {pending}</span> : current}
        </span>
      </div>
    </div>
  )
}
