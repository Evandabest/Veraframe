/**
 * Persistent character library (Step 50).
 *
 * Lists every installed character with its rich profile (description,
 * default emotion, TTS voice). Lets the user toggle selection for the
 * current project, edit a profile, or remove a user-uploaded character —
 * all from one place instead of the chip strip in AssetsPanel.
 */

import type { RegistryCharacterSummary } from '../../../preload'

export interface CharacterLibraryModalProps {
  open: boolean
  characters: RegistryCharacterSummary[]
  selectedCharacterIds: string[]
  onToggleCharacter: (id: string, checked: boolean) => void
  onEditCharacter: (id: string) => void
  onRemoveCharacter: (id: string) => void
  onAddCharacter: () => void
  onClose: () => void
}

export function CharacterLibraryModal({
  open,
  characters,
  selectedCharacterIds,
  onToggleCharacter,
  onEditCharacter,
  onRemoveCharacter,
  onAddCharacter,
  onClose
}: CharacterLibraryModalProps): React.JSX.Element | null {
  if (!open) return null
  const selected = new Set(selectedCharacterIds)

  return (
    <div
      onClick={onClose}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="flex w-full max-w-2xl flex-col gap-3 rounded-xl border border-neutral-700 bg-neutral-900 p-5 shadow-xl"
      >
        <header className="flex items-center justify-between">
          <div>
            <h3 className="text-base font-semibold text-neutral-100">Character library</h3>
            <p className="mt-0.5 text-xs text-neutral-400">
              Every installed character, with full profile. Toggle to add to or
              remove from the current project; click ✎ to edit the profile.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded border border-neutral-700 px-2 py-1 text-xs text-neutral-300 hover:bg-neutral-800"
          >
            Close
          </button>
        </header>

        <div className="flex max-h-[60vh] flex-col gap-2 overflow-y-auto">
          {characters.length === 0 ? (
            <p className="text-xs text-neutral-500">
              No characters installed. Use the + Add button below to upload one.
            </p>
          ) : (
            characters.map((c) => (
              <article
                key={c.id}
                className="flex items-start gap-3 rounded-lg border border-neutral-800 bg-neutral-950/60 p-3"
              >
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={selected.has(c.id)}
                    onChange={(e) => onToggleCharacter(c.id, e.target.checked)}
                  />
                </label>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-neutral-100">
                    {c.displayName}{' '}
                    <span className="ml-1 font-mono text-[10px] text-neutral-500">{c.id}</span>
                    {c.userProvided && (
                      <span className="ml-2 rounded bg-emerald-500/20 px-1.5 py-0.5 text-[10px] text-emerald-200">
                        yours
                      </span>
                    )}
                  </p>
                  {c.description ? (
                    <p className="mt-1 text-[11px] text-neutral-300">{c.description}</p>
                  ) : (
                    <p className="mt-1 text-[11px] italic text-neutral-500">
                      No description yet — click ✎ to add one.
                    </p>
                  )}
                  <div className="mt-1 flex gap-3 text-[11px] text-neutral-400">
                    {c.defaultEmotion && (
                      <span>
                        default emotion:{' '}
                        <span className="font-mono text-neutral-200">{c.defaultEmotion}</span>
                      </span>
                    )}
                    {c.voice && (
                      <span>
                        voice: <span className="font-mono text-neutral-200">{c.voice}</span>
                      </span>
                    )}
                  </div>
                </div>
                <div className="flex flex-shrink-0 items-center gap-1">
                  {c.userProvided && (
                    <>
                      <button
                        type="button"
                        onClick={() => onEditCharacter(c.id)}
                        title="Edit profile"
                        className="rounded border border-neutral-700 px-2 py-0.5 text-xs text-neutral-200 hover:bg-neutral-800"
                      >
                        ✎
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          if (window.confirm(`Remove "${c.displayName}" from the library?`)) {
                            onRemoveCharacter(c.id)
                          }
                        }}
                        title="Remove from library (deletes the user-uploaded files)"
                        className="rounded border border-red-500/60 bg-red-500/10 px-2 py-0.5 text-xs text-red-200 hover:bg-red-500/25"
                      >
                        ×
                      </button>
                    </>
                  )}
                </div>
              </article>
            ))
          )}
        </div>

        <footer className="flex items-center justify-between">
          <p className="text-[11px] text-neutral-500">
            {selected.size} selected / {characters.length} installed
          </p>
          <button
            type="button"
            onClick={onAddCharacter}
            className="rounded-md border border-emerald-500 bg-emerald-500/15 px-3 py-1 text-xs font-medium text-emerald-200 hover:bg-emerald-500/30"
          >
            + Add character
          </button>
        </footer>
      </div>
    </div>
  )
}
