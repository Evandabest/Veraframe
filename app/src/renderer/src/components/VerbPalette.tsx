/**
 * Floating palette of action verbs grouped by family.
 *
 * The palette is opened from a toolbar button and lets the user drag a
 * chip onto a timeline lane to add an action without typing a prompt.
 * The drag payload is the verb's action type — TimelinePanel reads it
 * via the `application/x-veraframe-verb` mime, computes the drop time
 * from the cursor's x position, and fires `onPaletteDrop`. App then
 * opens ActionEditor with the verb's prompt seed prefilled.
 *
 * This is additive — the existing `+` button and the prompt box still
 * route through the LLM. The palette is a shortcut for power users
 * who already know which action they want.
 */

import type { VerbDef } from '../verbs'
import { VERB_FAMILIES } from '../verbs'

export const VERB_DRAG_MIME = 'application/x-veraframe-verb'

export interface VerbPaletteProps {
  open: boolean
  onClose: () => void
}

export function VerbPalette({ open, onClose }: VerbPaletteProps): React.JSX.Element | null {
  if (!open) return null

  return (
    <div
      // Backdrop is transparent — the popover should not block timeline visibility,
      // but a click outside still dismisses it.
      onClick={onClose}
      className="fixed inset-0 z-40"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="absolute right-4 top-20 max-h-[70vh] w-80 overflow-y-auto rounded-xl border border-neutral-700 bg-neutral-900/95 p-3 shadow-2xl backdrop-blur"
      >
        <header className="mb-2 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-neutral-100">Verbs</h3>
          <button
            type="button"
            onClick={onClose}
            className="text-xs text-neutral-400 hover:text-neutral-200"
            title="Close palette"
          >
            ×
          </button>
        </header>

        <p className="mb-3 text-[11px] text-neutral-400">
          Drag a chip onto a timeline lane to insert that action. The
          existing prompt box and lane <code className="font-mono">+</code>{' '}
          buttons still route through the LLM.
        </p>

        <div className="flex flex-col gap-3">
          {VERB_FAMILIES.map((family) => (
            <section key={family.id}>
              <h4 className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-neutral-500">
                {family.label}
              </h4>
              <div className="flex flex-wrap gap-1.5">
                {family.verbs.map((verb) => (
                  <VerbChip key={verb.type} verb={verb} />
                ))}
              </div>
            </section>
          ))}
        </div>
      </div>
    </div>
  )
}

function VerbChip({ verb }: { verb: VerbDef }): React.JSX.Element {
  const onDragStart = (e: React.DragEvent<HTMLDivElement>): void => {
    e.dataTransfer.setData(VERB_DRAG_MIME, verb.type)
    e.dataTransfer.effectAllowed = 'copy'
  }

  return (
    <div
      draggable
      onDragStart={onDragStart}
      title={verb.description}
      className={`cursor-grab select-none rounded-md border px-2 py-1 font-mono text-[11px] active:cursor-grabbing ${
        verb.scene
          ? 'border-cyan-600/60 bg-cyan-600/15 text-cyan-200 hover:bg-cyan-600/25'
          : 'border-neutral-700 bg-neutral-800 text-neutral-200 hover:bg-neutral-700'
      }`}
    >
      {verb.label}
    </div>
  )
}
