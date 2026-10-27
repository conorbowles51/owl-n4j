import { useState, type ReactNode } from "react"

/** A labelled button that opens a panel: used instead of a collapsed <details>, so the control reads as a control. */
export function Disclosure({
  label,
  className,
  children,
  defaultOpen = false,
  onToggle,
}: {
  label: ReactNode
  className?: string
  children: ReactNode
  defaultOpen?: boolean
  onToggle?: (open: boolean) => void
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className={className}>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => {
          setOpen(!open)
          onToggle?.(!open)
        }}
        className="inline-flex items-center gap-1.5 rounded-md border bg-background px-3 py-1.5 text-sm font-semibold hover:bg-muted"
      >
        <span aria-hidden="true">{open ? "▾" : "▸"}</span>
        <span>{label}</span>
      </button>
      <div className={open ? "" : "hidden"}>{children}</div>
    </div>
  )
}
