/**
 * Mid-edit "+ Character" modal.
 *
 * Lets the user add a new character to the existing timeline without
 * re-prompting the whole scene. Pick a registered preset, a spawn point in
 * the active scene, give the character a handle, and we'll:
 *  - append a new entry to timeline.characters
 *  - insert a default idle action covering the full shot duration
 *  - trigger a full re-render (a new character is visible in every frame,
 *    so incremental splice/append cannot help us — every frame changes)
 */

import { useEffect, useState } from 'react'
import type { RegistryCharacterSummary, RegistrySceneSummary } from '../../../preload'

export interface AddCharacterModalProps {
  open: boolean
  /** All registered character presets, including bundled. */
  availableCharacters: RegistryCharacterSummary[]
  /** The active scene whose spawn points we offer. */
  scene: RegistrySceneSummary | null
  /** Character handles already in the timeline (to prevent collisions). */
  existingHandles: string[]
  onClose: () => void
  onConfirm: (payload: { preset: string; spawn: string; handle: string }) => void
}

export function AddCharacterModal(props: AddCharacterModalProps): React.JSX.Element | null {
  const { open, availableCharacters, scene, existingHandles, onClose, onConfirm } = props

  const [preset, setPreset] = useState<string>('')
  const [spawn, setSpawn] = useState<string>('')
  const [handle, setHandle] = useState<string>('')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    const first = availableCharacters[0]
    setPreset(first?.id ?? '')
    setSpawn(scene?.spawnPoints[0] ?? '')
    setHandle(uniqueHandle(first?.id ?? 'character', existingHandles))
    setError(null)
  }, [open, availableCharacters, scene, existingHandles])

  if (!open) return null

  const canSubmit =
    preset.length > 0 &&
    spawn.length > 0 &&
    handle.length > 0 &&
    /^[a-z0-9_]+$/i.test(handle) &&
    !existingHandles.includes(handle)

  const submit = (): void => {
    if (!canSubmit) {
      setError('Pick a preset, spawn point, and a unique handle (letters/digits/underscore only).')
      return
    }
    onConfirm({ preset, spawn, handle })
  }

  return (
    <div
      onClick={onClose}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="flex w-full max-w-md flex-col gap-4 rounded-xl border border-neutral-700 bg-neutral-900 p-5 shadow-xl"
      >
        <header>
          <h3 className="text-base font-semibold text-neutral-100">Add a character</h3>
          <p className="mt-1 text-xs text-neutral-400">
            Inserts a new character into the current timeline with a full-shot
            idle. The render will be a full re-render (every frame changes
            because there's now an extra figure in the scene).
          </p>
        </header>

        <div className="flex flex-col gap-3">
          <Field label="Preset">
            <select
              value={preset}
              onChange={(e) => setPreset(e.target.value)}
              className="w-full rounded border border-neutral-800 bg-neutral-950 px-2 py-1 text-sm focus:border-neutral-500 focus:outline-none"
            >
              {availableCharacters.length === 0 && (
                <option value="">No characters registered</option>
              )}
              {availableCharacters.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.displayName}
                  {c.userProvided ? ' (yours)' : ''}
                </option>
              ))}
            </select>
          </Field>

          <Field label="Spawn point">
            <select
              value={spawn}
              onChange={(e) => setSpawn(e.target.value)}
              disabled={!scene || scene.spawnPoints.length === 0}
              className="w-full rounded border border-neutral-800 bg-neutral-950 px-2 py-1 text-sm focus:border-neutral-500 focus:outline-none disabled:opacity-50"
            >
              {(!scene || scene.spawnPoints.length === 0) && (
                <option value="">No spawn points</option>
              )}
              {scene?.spawnPoints.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </Field>

          <Field
            label="Handle"
            hint="The short id actions refer to (e.g. 'student', 'robot'). Letters / digits / underscore only."
          >
            <input
              type="text"
              value={handle}
              onChange={(e) => setHandle(e.target.value)}
              className="w-full rounded border border-neutral-800 bg-neutral-950 px-2 py-1 font-mono text-sm focus:border-neutral-500 focus:outline-none"
            />
          </Field>
        </div>

        {error && <p className="text-xs text-red-400">{error}</p>}

        <footer className="flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-neutral-700 px-3 py-1.5 text-sm text-neutral-200 hover:bg-neutral-800"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={!canSubmit}
            className="rounded-md bg-emerald-600 px-4 py-1.5 text-sm font-semibold text-white hover:bg-emerald-500 disabled:cursor-not-allowed disabled:bg-neutral-700"
          >
            Add &amp; re-render
          </button>
        </footer>
      </div>
    </div>
  )
}

function uniqueHandle(base: string, taken: string[]): string {
  const sanitized = base.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '')
  if (!taken.includes(sanitized)) return sanitized
  let n = 2
  while (taken.includes(`${sanitized}_${n}`)) n += 1
  return `${sanitized}_${n}`
}

function Field({
  label,
  hint,
  children
}: {
  label: string
  hint?: string
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
