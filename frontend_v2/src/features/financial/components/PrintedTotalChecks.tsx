import type { z } from "zod"
import type { printedTotalChecks } from "../lib/printed-total-checks"
import { correctionMoney } from "../lib/correction-contract"
export function PrintedTotalChecks({
  checks,
  currency,
  title = "Printed transaction totals",
}: {
  checks: z.infer<typeof printedTotalChecks>
  currency: string
  title?: string
}) {
  return (
    <section aria-label={title} className="space-y-2 rounded border p-3">
      <h4 className="font-semibold">{title}</h4>
      {checks.checks.map((c) => (
        <div key={c.role}>
          <p>
            {c.role === "credits_total" ? "Money in" : "Money out"}:{" "}
            {c.status === "unavailable"
              ? "No printed total recorded"
              : c.status === "balanced"
                ? "Agrees with printed total"
                : "Differs from printed total"}
            .
          </p>
          <p className="text-sm">
            Counted: {correctionMoney(c.current_minor, currency)}
            {c.printed_minor !== null && (
              <>
                {" "}
                · Printed: {correctionMoney(c.printed_minor, currency)} ·
                Difference: {correctionMoney(c.difference_minor!, currency)}
              </>
            )}
          </p>
          {c.source && (
            <p className="text-sm">
              Original control text: {c.source.original_text}
            </p>
          )}
        </div>
      ))}
      <p className="text-sm">{checks.limitation}</p>
    </section>
  )
}
