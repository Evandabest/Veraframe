/**
 * Compact info button with a hover/click popover.
 *
 * Click to toggle, click outside to close. Used next to asset section
 * headings to surface "what files do I need to provide" instructions
 * without cluttering the main layout.
 */

import { useEffect, useRef, useState, type ReactNode } from 'react'

interface InfoTipProps {
  label: string
  children: ReactNode
}

export function InfoTip({ label, children }: InfoTipProps): React.JSX.Element {
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!open) return
    const onDocClick = (e: MouseEvent): void => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', onDocClick)
    return () => document.removeEventListener('mousedown', onDocClick)
  }, [open])

  return (
    <div ref={containerRef} className="relative inline-block">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label={label}
        title={label}
        className="inline-flex h-4 w-4 items-center justify-center rounded-full border border-neutral-600 text-[10px] font-bold leading-none text-neutral-400 hover:border-neutral-300 hover:text-neutral-100"
      >
        i
      </button>
      {open && (
        <div className="absolute left-5 top-0 z-40 w-80 rounded-md border border-neutral-700 bg-neutral-900 p-3 text-xs leading-relaxed text-neutral-200 shadow-xl">
          {children}
        </div>
      )}
    </div>
  )
}
