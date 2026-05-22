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
  // The primary file (mesh for characters, .blend for scenes) is auto-picked
  // when the modal opens. The two character-only animations are picked on
  // demand via their own buttons.
  const [filePath, setFilePath] = useState<string | null>(null)
  const [idlePath, setIdlePath] = useState<string | null>(null)
  const [walkPath, setWalkPath] = useState<string | null>(null)
  const [pickerError, setPickerError] = useState<string | null>(null)
  const [id, setId] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [description, setDescription] = useState('')
  const [spawnPoints, setSpawnPoints] = useState('door, center_room')
  const [cameraPresets, setCameraPresets] = useState('wide')
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  // Reset form when the modal opens. We deliberately do NOT auto-open the OS
  // file picker — the user needs to see the description first and decide
  // whether to proceed. They click "Pick file…" to open Finder.
  useEffect(() => {
    if (!open) return
    setFilePath(null)
    setIdlePath(null)
    setWalkPath(null)
    setPickerError(null)
    setId('')
    setDisplayName('')
    setDescription('')
    setSpawnPoints('door, center_room')
    setCameraPresets('wide')
    setSubmitting(false)
    setSubmitError(null)
  }, [open, kind])

  const pickMainFile = async (): Promise<void> => {
    setPickerError(null)
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
    }
  }

  const pickAuxFile = async (
    setter: (p: string) => void
  ): Promise<void> => {
    const result = await window.veraframe.pickAssetFile('character')
    if (result.ok) setter(result.filePath)
  }

  if (!open) return null

  const canSubmit =
    !!filePath &&
    /^[a-z0-9_]+$/i.test(id) &&
    displayName.trim().length > 0 &&
    (kind !== 'scene' || spawnPoints.trim().length > 0) &&
    (kind !== 'character' || (!!idlePath && !!walkPath))

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
              idlePath: idlePath!,
              walkPath: walkPath!,
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
              ? 'Pick a .blend file; we’ll copy it to the user-data dir and write a manifest. The names you give for spawn points and cameras must match the Empty / Camera object names inside the .blend. Tip: rotate each spawn-point Empty to set the character’s starting facing — Empties left at the default (0,0,0) auto-rotate the character toward the active camera.'
              : 'Pick a .fbx mesh + your own idle.fbx and walk.fbx animations. The rig must be Mixamo-style (matching bone names) so the animation library binds correctly.'}
          </p>
        </header>

        {pickerError && <p className="text-xs text-red-400">{pickerError}</p>}

        <FilePickerField
          label={kind === 'scene' ? 'Scene file (.blend)' : 'Character mesh (.fbx)'}
          hint={
            kind === 'scene'
              ? 'The .blend file containing the scene geometry, spawn-point Empties, and Camera objects.'
              : 'The .fbx mesh with the Mixamo-style rig.'
          }
          value={filePath}
          onPick={pickMainFile}
        />

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

            {kind === 'character' && (
              <>
                <FilePickerField
                  label="Idle animation (.fbx)"
                  hint="Mixamo-style idle clip. Bone names must match the mesh rig."
                  value={idlePath}
                  onPick={() => pickAuxFile(setIdlePath)}
                />
                <FilePickerField
                  label="Walk animation (.fbx)"
                  hint="Mixamo walk-in-place clip (no root motion). The executor adds the translation curve."
                  value={walkPath}
                  onPick={() => pickAuxFile(setWalkPath)}
                />
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
            title={!filePath ? 'Pick a file first' : undefined}
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

function FilePickerField({
  label,
  hint,
  value,
  onPick
}: {
  label: string
  hint: string
  value: string | null
  onPick: () => void
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
          {value ? 'Change…' : 'Pick file…'}
        </button>
        <span className="flex-1 truncate font-mono text-[11px] text-neutral-500" title={value ?? ''}>
          {value ?? '(none picked)'}
        </span>
      </div>
      {hint && <span className="text-[10px] text-neutral-500">{hint}</span>}
    </div>
  )
}
