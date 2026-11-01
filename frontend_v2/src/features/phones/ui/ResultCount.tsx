import type { ReactNode } from "react"
import { cn } from "@/lib/cn"

/**
 * The one count wording (07 4.8): "Showing 1,204 of 1,260 messages", thousands separators, the reason and how to
 * see the rest. "N / M" is never used, and there is no "Load more". Totals state "N not yet confirmed" whenever
 * the result holds unconfirmed readings (4.6). While a phone is still being read, "(so far)" follows the count.
 */
export interface ResultCountProps {
  shown: number
  total: number
  /** Plural noun, e.g. "messages". */
  noun: string
  singular?: string
  /** Why fewer are shown, e.g. "the date filter removed 56". */
  reason?: string
  /** A control or sentence saying how to see the rest. */
  rest?: ReactNode
  unconfirmed?: number
  soFar?: boolean
  className?: string
}

export const fmt = (n: number) => n.toLocaleString("en-US")

export function countSentence({ shown, total, noun, singular, soFar }: Pick<ResultCountProps, "shown" | "total" | "noun" | "singular" | "soFar">): string {
  const word = total === 1 ? (singular ?? noun.replace(/s$/, "")) : noun
  const tail = soFar ? " (so far)" : ""
  if (shown >= total) return `${fmt(total)} ${word}${tail}`
  return `Showing ${fmt(shown)} of ${fmt(total)} ${word}${tail}`
}

export function ResultCount(props: ResultCountProps) {
  const { reason, rest, unconfirmed, className } = props
  return (
    <p className={cn("flex flex-wrap items-baseline gap-x-2 text-sm text-foreground", className)} data-testid="result-count" aria-live="polite">
      <span className="font-medium">{countSentence(props)}</span>
      {props.shown < props.total && reason && <span className="text-muted-foreground">{reason}.</span>}
      {props.shown < props.total && rest}
      {!!unconfirmed && unconfirmed > 0 && (
        <span className="text-status-review">{fmt(unconfirmed)} not yet confirmed</span>
      )}
    </p>
  )
}
