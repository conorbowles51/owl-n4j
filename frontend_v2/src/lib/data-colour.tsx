/**
 * Data colour inside content (lx-style, Neil 2 Nov 2026: "all, build them"). The shell, surfaces and Loupe red stay
 * as they are; these colours mark direction, source, app, kind and what needs a person, always with a word, arrow or
 * name beside them (colour never stands alone). Tokens live in styles/globals.css and are checked for contrast in
 * features/phones/ui/tokens.test.ts. Class names are literal so Tailwind sees them.
 */
import { cn } from "@/lib/cn"

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

export const SOURCE_TONES = [
  { text: "text-source-1", border: "border-source-1", bg: "bg-source-1", edge: "shadow-[inset_4px_0_0_hsl(var(--source-1))]" },
  { text: "text-source-2", border: "border-source-2", bg: "bg-source-2", edge: "shadow-[inset_4px_0_0_hsl(var(--source-2))]" },
  { text: "text-source-3", border: "border-source-3", bg: "bg-source-3", edge: "shadow-[inset_4px_0_0_hsl(var(--source-3))]" },
  { text: "text-source-4", border: "border-source-4", bg: "bg-source-4", edge: "shadow-[inset_4px_0_0_hsl(var(--source-4))]" },
] as const

const hash = (s: string) => [...s].reduce((a, c) => (a * 31 + c.charCodeAt(0)) >>> 0, 7)

/** One stable colour per account or source key (the account's name is always shown beside it). */
export function sourceTone(key: string) {
  return SOURCE_TONES[hash(key || "?") % SOURCE_TONES.length]
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

const APP_TONES = [
  { text: "text-app-1", border: "border-app-1", bg: "bg-app-1", soft: "bg-app-1-soft" },
  { text: "text-app-2", border: "border-app-2", bg: "bg-app-2", soft: "bg-app-2-soft" },
  { text: "text-app-3", border: "border-app-3", bg: "bg-app-3", soft: "bg-app-3-soft" },
  { text: "text-app-4", border: "border-app-4", bg: "bg-app-4", soft: "bg-app-4-soft" },
] as const
const KNOWN_APPS: Record<string, number> = { whatsapp: 0, telegram: 1, signal: 2, "native messages": 3, sms: 3, imessage: 3 }

/** One colour per phone app, the same on every phone screen (the app's name is always shown beside it). */
export function appTone(app: string) {
  const known = KNOWN_APPS[app.trim().toLowerCase()]
  return APP_TONES[known ?? hash(app.toLowerCase()) % APP_TONES.length]
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
