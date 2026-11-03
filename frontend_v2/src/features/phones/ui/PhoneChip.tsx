import { cn } from "@/lib/cn"
import { phoneMark, SHAPE_PATHS } from "../lib/phone-palette"
import { phoneChipText } from "./phone-chip-text"

/**
 * A phone's chip (07 4.5, 4.11): its colour and marker shape, always with the label; the extraction date is added
 * when two phones in the case share a label ("C1 · 3 May").
 */
export interface PhoneChipProps {
  label: string
  /** Position of the phone in the case's stable order (palette index). */
  index: number
  extractionDate?: string
  /** True when another phone in the case has the same label. */
  collides?: boolean
  onRemove?: () => void
  className?: string
}

export function PhoneShape({ index, className }: { index: number; className?: string }) {
  const mark = phoneMark(index)
  return (
    <svg viewBox="0 0 16 16" className={cn("size-3.5 shrink-0", className)} aria-hidden fillRule="evenodd">
      <path d={SHAPE_PATHS[mark.shape]} className="fill-[var(--phone-light)] dark:fill-[var(--phone-dark)]" style={{ ["--phone-light" as string]: mark.light, ["--phone-dark" as string]: mark.dark }} />
    </svg>
  )
}

export function PhoneChip(props: PhoneChipProps) {
  const text = phoneChipText(props)
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-sm border bg-card px-1.5 py-0.5 text-xs font-medium text-foreground", props.className)} data-phone={props.label}>
      <PhoneShape index={props.index} />
      <span>{text}</span>
      {props.onRemove && (
        <button type="button" onClick={props.onRemove} aria-label={`Remove ${text}`} className="ml-0.5 rounded-sm px-0.5 text-muted-foreground hover:text-foreground">
          ×
        </button>
      )}
    </span>
  )
}
