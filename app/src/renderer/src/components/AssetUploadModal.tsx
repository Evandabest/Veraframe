/**
 * Modal for uploading a new scene or character.
 *
 * Flow:
 *   1. User clicks "+ Add scene/character" in AssetsPanel; we open this modal
 *      and immediately fire the file picker via IPC.
 *   2. Once a file is picked, the modal collects metadata (id, display name,
 *      and for scenes the spawn-point + camera names).
 *   3. Submit calls addScene / addCharacter IPC; on success, parent refreshes
 *      the registry and closes the modal.
 */

import { useEffect, useState } from 'react'

export type AssetKind = 'scene' | 'character'

export interface AssetUploadModalProps {
  open: boolean
  kind: AssetKind
  onClose: () => void
  onSubmitted: (id: string) => void
}

export function AssetUploadModal({
  open,
  kind,
  onClose,
  onSubmitted
}: AssetUploadModalProps): React.JSX.Element | null {
  const [filePath, setFilePath] = useState<string | null>(null)
  const [pickerError, setPickerError] = useState<string | null>(null)
  const [id, setId] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [description, setDescription] = useState('')
  const [spawnPoints, setSpawnPoints] = useState('door, center_room')
  const [cameraPresets, setCameraPresets] = useState('wide')
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  // Reset form + auto-open the OS file picker each time the modal opens.
  useEffect(() => {
    if (!open) return
    setFilePath(null)
    setPickerError(null)
    setId('')
    setDisplayName('')
    setDescription('')
    setSpawnPoints('door, center_room')
    setCameraPresets('wide')
    setSubmitting(false)
    setSubmitError(null)
    ;(async () => {
      const result = await window.veraframe.pickAssetFile(kind)
      if (result.ok) {
        setFilePath(result.filePath)
        // Auto-fill an id and display name from the chosen filename.
        const base = result.filePath.replace(/^.*[\\/]/, '').replace(/\.[^.]+$/, '')
        const sanitized = base.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '')
        setId(sanitized)
        setDisplayName(base)
      } else if (result.error !== 'picker canceled') {
        setPickerError(result.error)
      } else {
        // Canceled the picker → close the modal so the user isn't stuck.
        onClose()
      }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, kind])

  if (!open) return null

  const canSubmit =
    !!filePath &&
    /^[a-z0-9_]+$/i.test(id) &&
    displayName.trim().length > 0 &&
    (kind !== 'scene' || spawnPoints.trim().length > 0)

  const onSubmit = async (): Promise<void> => {
    if (!filePath) return
    setSubmitError(null)
    setSubmitting(true)
    try {
      const spawnList = spawnPoints
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean)
      const cameraList = cameraPresets
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean)
      const response =
        kind === 'scene'
          ? await window.veraframe.addScene({
              sourcePath: filePath,
              id,
              displayName,
              description: description || undefined,
              spawnPoints: spawnList,
              cameraPresets: cameraList
            })
          : await window.veraframe.addCharacter({
              sourcePath: filePath,
              id,
              displayName,
              description: description || undefined
            })
      if (response.ok) {
        onSubmitted(response.id)
      } else {
        setSubmitError(response.error)
      }
    } finally {
      setSubmitting(false)
    }
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
        <header>
          <h3 className="text-base font-semibold text-neutral-100">
            Add {kind === 'scene' ? 'a scene' : 'a character'}
          </h3>
          <p className="mt-1 text-xs text-neutral-400">
            {kind === 'scene'
              ? 'Pick a .blend file; we’ll copy it to the user-data dir and write a manifest. The names you give for spawn points and cameras must match the Empty / Camera object names inside the .blend.'
              : 'Pick a .fbx file with a Mixamo-style rig. The character will become available in the picker for the LLM to use.'}
          </p>
        </header>

        {pickerError && <p className="text-xs text-red-400">{pickerError}</p>}

        {filePath && (
          <p className="break-all rounded-md border border-neutral-800 bg-neutral-950 p-2 text-xs text-neutral-400">
            <span className="text-neutral-500">file:</span> {filePath}
          </p>
        )}

        {filePath && (
          <div className="flex flex-col gap-3">
            <Field label="ID" hint="lowercase letters, digits, underscore only">
              <input
                type="text"
                value={id}
                onChange={(e) => setId(e.target.value)}
                placeholder="my_scene"
                className="w-full rounded border border-neutral-800 bg-neutral-950 px-2 py-1 font-mono text-sm focus:border-neutral-500 focus:outline-none"
              />
            </Field>
            <Field label="Display name" hint="shown in the UI dropdown">
              <input
                type="text"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                className="w-full rounded border border-neutral-800 bg-neutral-950 px-2 py-1 text-sm focus:border-neutral-500 focus:outline-none"
              />
            </Field>
            <Field label="Description (optional)" hint="">
              <input
                type="text"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="w-full rounded border border-neutral-800 bg-neutral-950 px-2 py-1 text-sm focus:border-neutral-500 focus:outline-none"
              />
            </Field>

            {kind === 'scene' && (
              <>
                <Field
                  label="Spawn points"
                  hint="comma-separated; each must match an Empty object name in the .blend"
                >
                  <input
                    type="text"
                    value={spawnPoints}
                    onChange={(e) => setSpawnPoints(e.target.value)}
                    placeholder="door, center_room, far_corner"
                    className="w-full rounded border border-neutral-800 bg-neutral-950 px-2 py-1 font-mono text-sm focus:border-neutral-500 focus:outline-none"
                  />
                </Field>
                <Field
                  label="Camera presets"
                  hint="comma-separated; each must match a Camera object name"
                >
                  <input
                    type="text"
                    value={cameraPresets}
                    onChange={(e) => setCameraPresets(e.target.value)}
                    placeholder="wide, close"
                    className="w-full rounded border border-neutral-800 bg-neutral-950 px-2 py-1 font-mono text-sm focus:border-neutral-500 focus:outline-none"
                  />
                </Field>
              </>
            )}
          </div>
        )}

        {submitError && <p className="text-xs text-red-400">{submitError}</p>}

        <footer className="flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="rounded-md border border-neutral-700 px-3 py-1.5 text-sm text-neutral-200 hover:bg-neutral-800 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onSubmit}
            disabled={!canSubmit || submitting}
            className="rounded-md bg-emerald-600 px-4 py-1.5 text-sm font-semibold text-white hover:bg-emerald-500 disabled:cursor-not-allowed disabled:bg-neutral-700"
          >
            {submitting ? 'Adding…' : 'Add'}
          </button>
        </footer>
      </div>
    </div>
  )
}

function Field({
  label,
  hint,
  children
}: {
  label: string
  hint: string
  children: React.ReactNode
}): React.JSX.Element {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-xs text-neutral-400">{label}</label>
      {children}
      {hint && <span className="text-[10px] text-neutral-500">{hint}</span>}
    </div>
  )
}
