import { cn } from "@/lib/cn"
import type { Badge } from "../lib/badges"

/**
 * Record state badges (03 section 3.5): words, never colour alone, each with the captured value on hover, in
 * priority order (corrected, not confirmed, deleted or recovered, from another device, duplicate, then others); two
 * are shown and "+N" lists the rest. Every one of 01 section 7.2's file outcomes other than a match has its badge.
 */

const TONE = {
  review: "text-status-review bg-status-review-soft",
  deleted: "text-status-deleted bg-status-deleted-soft",
  plain: "text-foreground bg-muted",
}

export function StateBadges({ badges, max = 2 }: { badges: Badge[]; max?: number }) {
  if (!badges.length) return null
  const shown = badges.slice(0, max)
  const rest = badges.slice(max)
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      {shown.map((b) => (
        <span key={b.words} className={cn("rounded-sm px-1.5 py-0.5 text-xs font-medium", TONE[b.tone])} title={b.hover}>
          {b.words}
        </span>
      ))}
      {rest.length > 0 && (
        <span className="rounded-sm bg-muted px-1.5 py-0.5 text-xs font-medium" title={rest.map((b) => b.words).join(", ")} aria-label={`${rest.length} more: ${rest.map((b) => b.words).join(", ")}`}>
          +{rest.length}
        </span>
      )}
    </span>
  )
}
