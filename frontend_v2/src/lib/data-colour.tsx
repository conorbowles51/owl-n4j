/**
 * Data colour inside content (lx-style, Neil 2 Nov 2026: "all, build them"). The shell, surfaces and Loupe red stay
 * as they are; these colours mark direction, source, app, kind and what needs a person, always with a word, arrow or
 * name beside them (colour never stands alone). Tokens live in styles/globals.css and are checked for contrast in
 * features/phones/ui/tokens.test.ts. Class names are literal so Tailwind sees them.
 */
import { cn } from "@/lib/cn"
import { sourceTone, SOURCE_TONES } from "./data-tone"

export type Direction = "in" | "out"

export const MONEY = {
  in: { text: "text-money-in", edge: "shadow-[inset_4px_0_0_hsl(var(--money-in))]", border: "border-l-money-in" },
  out: { text: "text-money-out", edge: "shadow-[inset_4px_0_0_hsl(var(--money-out))]", border: "border-l-money-out" },
} as const

/** "↓ in" / "↑ out" beside an amount, in the direction's colour. */
export function DirectionMark({ direction, className }: { direction: Direction; className?: string }) {
  return (
    <span data-direction={direction} className={cn("text-[11px] font-semibold", MONEY[direction].text, className)}>
      {direction === "in" ? "↓ in" : "↑ out"}
    </span>
  )
}

/** An account / source tag: a coloured square and the name, in that source's colour. */
export function SourceTag({ sourceKey, children, title }: { sourceKey: string; children: React.ReactNode; title?: string }) {
  const tone = sourceTone(sourceKey)
  return (
    <span
      data-source-tone={SOURCE_TONES.indexOf(tone) + 1}
      title={title}
      className={cn("inline-flex max-w-full items-center gap-1 rounded border px-1.5 font-semibold", tone.text, tone.border)}
    >
      <span aria-hidden="true" className={cn("size-[7px] shrink-0 rounded-[2px]", tone.bg)} />
      <span className="truncate">{children}</span>
    </span>
  )
}

/** A short bar showing a value against the largest in view; the number itself stays beside it. */
export function ShareBar({
  value,
  max,
  className,
  barClassName = "bg-status-info",
  width = "w-16",
}: {
  value: number
  max: number
  className?: string
  barClassName?: string
  width?: string
}) {
  const pct = max > 0 ? Math.max(4, Math.min(100, Math.round((value / max) * 100))) : 0
  return (
    <span
      aria-hidden="true"
      data-share-bar={pct}
      className={cn("ml-2 inline-block h-1.5 overflow-hidden rounded-full bg-status-info-soft align-middle", width, className)}
    >
      <span className={cn("block h-full rounded-full", barClassName)} style={{ width: `${pct}%` }} />
    </span>
  )
}

/** The "needs a person" tag: amber with words, never colour alone. */
export function CheckTag({ children = "To check", className }: { children?: React.ReactNode; className?: string }) {
  return (
    <span
      data-check-tag=""
      className={cn(
        "inline-flex items-center gap-1 rounded-full border border-status-warning bg-status-warning-soft px-2 text-[11px] font-bold tracking-[0.02em] text-status-warning",
        className,
      )}
    >
      {children}
    </span>
  )
}
