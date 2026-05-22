/**
 * Per-file edit modal for a user-uploaded scene.
 *
 * Mirrors `EditCharacterModal` but for the scene asset type. The user can:
 *   - Replace the scene file (.blend or .fbx)
 *   - Edit display name, spawn-point names, camera preset names
 *
 * Only changed fields are submitted; unchanged ones stay as they are.
 */

import { useEffect, useState } from 'react'

export interface EditSceneModalProps {
  open: boolean
  sceneId: string
  initialDisplayName: string
  initialSpawnPoints: string[]
  initialCameraPresets: string[]
  onClose: () => void
  onSaved: () => void
}

export function EditSceneModal(props: EditSceneModalProps): React.JSX.Element | null {
  const {
    open,
    sceneId,
    initialDisplayName,
    initialSpawnPoints,
    initialCameraPresets
  } = props

  const [displayName, setDisplayName] = useState(initialDisplayName)
  const [spawnPoints, setSpawnPoints] = useState(initialSpawnPoints.join(', '))
  const [cameraPresets, setCameraPresets] = useState(initialCameraPresets.join(', '))
  const [newScene, setNewScene] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setDisplayName(initialDisplayName)
    setSpawnPoints(initialSpawnPoints.join(', '))
    setCameraPresets(initialCameraPresets.join(', '))
    setNewScene(null)
    setError(null)
    setSubmitting(false)
  }, [open, sceneId, initialDisplayName, initialSpawnPoints, initialCameraPresets])

  if (!open) return null

  const pickScene = async (): Promise<void> => {
    const result = await window.veraframe.pickAssetFile('scene')
    if (result.ok) setNewScene(result.filePath)
  }

  const initialSpawnStr = initialSpawnPoints.join(', ')
  const initialCameraStr = initialCameraPresets.join(', ')
  const hasChange =
    newScene !== null ||
    displayName !== initialDisplayName ||
    spawnPoints !== initialSpawnStr ||
    cameraPresets !== initialCameraStr

  const onSave = async (): Promise<void> => {
    setError(null)
    setSubmitting(true)
    const parseList = (s: string): string[] =>
      s.split(',').map((x) => x.trim()).filter(Boolean)
    const response = await window.veraframe.updateScene({
      id: sceneId,
      scenePath: newScene,
      displayName: displayName !== initialDisplayName ? displayName : null,
      spawnPoints: spawnPoints !== initialSpawnStr ? parseList(spawnPoints) : null,
      cameraPresets:
        cameraPresets !== initialCameraStr ? parseList(cameraPresets) : null
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
            Edit scene · <span className="font-mono">{sceneId}</span>
          </h3>
          <p className="mt-1 text-xs text-neutral-400">
            Replace the .blend/.fbx file or update the manifest fields. Unchanged
            entries stay as they are.
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
            <label className="text-xs text-neutral-400">Scene file</label>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={pickScene}
                className="rounded border border-neutral-700 bg-neutral-950 px-3 py-1 text-xs text-neutral-200 hover:border-neutral-500"
              >
                {newScene ? 'Pick again…' : 'Replace…'}
              </button>
              {newScene && (
                <button
                  type="button"
                  onClick={() => setNewScene(null)}
                  className="rounded border border-neutral-700 px-2 py-1 text-xs text-neutral-400 hover:text-neutral-200"
                >
                  keep current
                </button>
              )}
              <span
                className="flex-1 truncate font-mono text-[11px] text-neutral-500"
                title={newScene ?? 'current scene.{blend,fbx} on disk'}
              >
                {newScene ? (
                  <span className="text-emerald-300">→ {newScene}</span>
                ) : (
                  '(unchanged)'
                )}
              </span>
            </div>
          </div>

          <div className="flex flex-col gap-1">
            <label className="text-xs text-neutral-400">Spawn points</label>
            <input
              type="text"
              value={spawnPoints}
              onChange={(e) => setSpawnPoints(e.target.value)}
              placeholder="door, center_room, far_corner"
              className="w-full rounded border border-neutral-800 bg-neutral-950 px-2 py-1 font-mono text-sm focus:border-neutral-500 focus:outline-none"
            />
            <span className="text-[10px] text-neutral-500">
              Comma-separated; each must match an Empty object name in the
              scene file.
            </span>
          </div>

          <div className="flex flex-col gap-1">
            <label className="text-xs text-neutral-400">Camera presets</label>
            <input
              type="text"
              value={cameraPresets}
              onChange={(e) => setCameraPresets(e.target.value)}
              placeholder="wide, close"
              className="w-full rounded border border-neutral-800 bg-neutral-950 px-2 py-1 font-mono text-sm focus:border-neutral-500 focus:outline-none"
            />
            <span className="text-[10px] text-neutral-500">
              Comma-separated; each must match a Camera object name.
            </span>
          </div>
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
