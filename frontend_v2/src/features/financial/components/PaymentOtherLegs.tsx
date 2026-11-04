import { useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { fetchAPI } from "@/lib/api-client"
import { LevelBadge } from "@/features/phones/analysis/MoneyPairings"
import { Disclosure } from "./Disclosure"

type Level = "strong" | "moderate" | "weak" | "faint"
interface OtherLeg {
  transaction_id: string
  date: string
  direction: string
  description: string | null
  holder: string | null
  institution: string | null
  identifier: string | null
  gap_days: number
  level: Level
  is_the_named_leg: boolean
  reasons: { match: string[]; substantiation: string[]; against: string[] }
}
interface OtherLegs {
  transaction_id: string
  named_from: string | null
  candidates: OtherLeg[]
  by_level: Record<Level, number>
  left_out: { beyond_days: number; search_days: number }
  rule: string
  reason?: string
}

/**
 * Every possible other leg of this payment in another account of the case, strongest first, each with its strength
 * by a stated rule and its reasons (read when opened). A candidate is never used as the payment's name; the leg the
 * shown name comes from, if any, is marked.
 */
export function PaymentOtherLegs({ caseId, transactionId, onOpen }: { caseId: string; transactionId: string; onOpen?: (id: string) => void }) {
  const [open, setOpen] = useState(false)
  const legs = useQuery({
    queryKey: ["financial-payment-other-legs", caseId, transactionId],
    enabled: open,
    queryFn: () =>
      fetchAPI<OtherLegs>(
        `/api/financial/payment-other-legs?case_id=${encodeURIComponent(caseId)}&transaction_id=${encodeURIComponent(transactionId)}`
      ),
  })
  const d = legs.data
  return (
    <Disclosure label="Possible other legs of this payment" onToggle={setOpen}>
      <div className="space-y-2 text-sm" aria-label="Possible other legs">
        {legs.isLoading && <p role="status">Looking for payments of the same amount in the case’s other accounts…</p>}
        {legs.isError && <p role="alert">The possible other legs could not be loaded. {legs.error instanceof Error ? legs.error.message : ""}</p>}
        {d && (
          <>
            <p>
              {d.candidates.length === 0
                ? d.reason ?? "No payment of the same currency and amount in another account of the case within 365 days."
                : `${d.candidates.length} possible: ${(["strong", "moderate", "weak", "faint"] as const).map((lv) => `${d.by_level[lv] ?? 0} ${lv}`).join(", ")}.`}
              {d.left_out.beyond_days > 0 ? ` ${d.left_out.beyond_days} more than ${d.left_out.search_days} days away are counted, not listed.` : ""}
            </p>
            <p className="text-xs text-muted-foreground">{d.rule}</p>
            <ul className="space-y-2">
              {d.candidates.map((c) => (
                <li key={c.transaction_id} className="space-y-1 rounded border p-2" aria-label={`Possible other leg ${c.date}`}>
                  <p className="flex flex-wrap items-center gap-2">
                    <LevelBadge level={c.level} />
                    <span>
                      {c.direction === "credit" ? "Money in" : "Money out"} · {[c.holder, c.institution, c.identifier].filter(Boolean).join(" · ")} · {c.date}
                    </span>
                    {c.is_the_named_leg && <span className="text-xs font-semibold">the name shown comes from this payment</span>}
                  </p>
                  <p className="text-xs">{c.description ?? "No description"}</p>
                  <p className="text-xs">How well matched: {c.reasons.match.join("; ")}</p>
                  <p className="text-xs">How substantiated: {c.reasons.substantiation.join("; ") || "nothing beyond the match"}</p>
                  {c.reasons.against.length > 0 && <p className="text-xs">Against: {c.reasons.against.join("; ")}</p>}
                  {onOpen && (
                    <button type="button" className="text-xs underline" onClick={() => onOpen(c.transaction_id)}>
                      Open this payment
                    </button>
                  )}
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </Disclosure>
  )
}
