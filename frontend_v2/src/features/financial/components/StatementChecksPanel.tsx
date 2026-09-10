import { statementDeltaHints } from "../lib/statement-delta-hints"
import { StatementDeltaHintsPanel } from "./StatementDeltaHintsPanel"
import { printedTotalChecks } from "../lib/printed-total-checks"
import { PrintedTotalChecks } from "./PrintedTotalChecks"
import { StatementRunningBalances } from "./StatementRunningBalances"
import { StatementSourceButton } from "./StatementSourceButton"
import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { z } from "zod"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import { assertCandidateScope, candidateUrl } from "../lib/candidate-contract"
import { correctionMoney } from "../lib/correction-contract"

const count = z.number().int().nonnegative()
const minor = z.string().regex(/^-?(0|[1-9][0-9]*)$/)
const day = z
  .string()
  .regex(/^\d{4}-\d{2}-\d{2}$/)
  .nullable()
const amounts = z.object({
  opening: minor.nullable(),
  credits: minor,
  debits: minor,
  computed_closing: minor.nullable(),
  closing: minor.nullable(),
  difference: minor.nullable(),
})
const item = z
  .object({
    period_id: z.string(),
    account_id: z.string(),
    account_label: z.string(),
    source_document_id: z.string(),
    source_status: z.string(),
    proof_class: z.enum(["p0", "p1", "p2", "p3"]),
    currency: z.string(),
    start: day,
    end: day,
    opening_source: z.string(),
    closing_source: z.string(),
    recorded_status: z.string(),
    recorded_at: z.string().nullable(),
    status: z.enum(["balanced", "unbalanced", "unavailable", "refused"]),
    reason: z.string().nullable(),
    amounts: amounts.nullable(),
    counted_rows: count.nullable(),
    excluded_rows: count.nullable(),
    independent: z.boolean().nullable(),
    delta_hints: statementDeltaHints.nullable().optional(),
    printed_totals: printedTotalChecks.nullable().optional(),
    printed_totals_error: z.string().nullable().optional(),
  })
  .refine((v) => {
    if (
      v.delta_hints?.available &&
      v.delta_hints.difference_minor !== v.amounts?.difference
    )
      return false
    if (v.status === "refused") return v.amounts === null && v.reason !== null
    if (
      !v.amounts ||
      v.counted_rows === null ||
      v.excluded_rows === null ||
      v.independent === null
    )
      return false
    const a = v.amounts
    if (v.status === "unavailable")
      return (
        (a.opening === null || a.closing === null) &&
        a.computed_closing === null &&
        a.difference === null
      )
    return (
      a.opening !== null &&
      a.closing !== null &&
      a.computed_closing !== null &&
      a.difference !== null &&
      BigInt(a.opening) + BigInt(a.credits) - BigInt(a.debits) ===
        BigInt(a.computed_closing) &&
      BigInt(a.computed_closing) - BigInt(a.closing) === BigInt(a.difference) &&
      (v.status === "balanced") === (BigInt(a.difference) === 0n)
    )
  }, "Statement check arithmetic is inconsistent.")
const report = z.object({
  case_id: z.string(),
  offset: count,
  has_more: z.boolean(),
  applied: z.literal(false),
  checked_at: z.string(),
  limitation: z.string(),
  items: z.array(item).max(25),
})
const statusLabel = {
  balanced: "Balances agree",
  unbalanced: "Balance difference",
  unavailable: "Missing balances",
  refused: "Could not check",
}
const fields = [
  ["opening", "Opening balance"],
  ["credits", "Money in"],
  ["debits", "Money out"],
  ["computed_closing", "Calculated closing balance"],
  ["closing", "Recorded closing balance"],
  ["difference", "Difference"],
] as const

export function StatementChecksPanel({
  caseId,
}: {
  caseId: string | undefined
}) {
  const [opened, setOpened] = useState(false),
    [offset, setOffset] = useState(0)
  const query = useQuery({
    queryKey: ["financial-ledger", caseId, "statement-checks", offset],
    enabled: opened && Boolean(caseId),
    retry: false,
    queryFn: async () => {
      const data = report.parse(
        await fetchAPI<unknown>(
          `${candidateUrl("statement-checks", caseId!)}&offset=${offset}`
        )
      )
      assertCandidateScope(data, caseId!)
      if (data.offset !== offset)
        throw new Error("Statement page changed. Refresh the check.")
      return data
    },
  })
  if (!caseId) return <p>Choose a case to check statement balances.</p>
  return (
    <section
      className="space-y-3 rounded border p-4"
      aria-label="Statement balance checks"
    >
      <h3 className="font-semibold">Statement balance checks</h3>
      <p>
        Compare opening balance plus money in minus money out with the recorded
        closing balance. Missing balances remain unknown.
      </p>
      <Button
        variant="outline"
        disabled={query.isFetching}
        onClick={() => (opened ? void query.refetch() : setOpened(true))}
      >
        {opened ? "Refresh balance checks" : "Check statement balances"}
      </Button>
      {opened &&
        (query.isPending ? (
          <p role="status">Checking current statement balances…</p>
        ) : query.isError ? (
          <p role="alert">Balance checks unavailable. {query.error.message}</p>
        ) : (
          <>
            <p className="text-sm">
              Checked at {query.data.checked_at}. {query.data.limitation}
            </p>
            {query.data.items.length === 0 && (
              <p>
                No statement periods on this page. This does not establish
                complete extraction.
              </p>
            )}
            {query.data.items.map((period) => (
              <article
                key={period.period_id}
                className="space-y-3 rounded border p-3"
              >
                <div className="flex flex-wrap justify-between gap-2">
                  <h4 className="font-semibold">
                    {period.account_label} · {period.currency}
                  </h4>
                  <strong>{statusLabel[period.status]}</strong>
                </div>
                <p>
                  {period.start ?? "Unknown start"} to{" "}
                  {period.end ?? "unknown end"}
                </p>
                <p>
                  Source: {period.source_status} ·{" "}
                  {period.proof_class.toUpperCase()}. These checks do not change
                  source eligibility.
                </p>
                {period.delta_hints && (
                  <StatementDeltaHintsPanel
                    key={`${query.data.checked_at}:${period.period_id}`}
                    caseId={caseId}
                    currency={period.currency}
                    hints={period.delta_hints}
                  />
                )}
                {period.printed_totals && (
                  <PrintedTotalChecks
                    checks={period.printed_totals}
                    currency={period.currency}
                  />
                )}
                {period.printed_totals_error && (
                  <p role="alert">
                    Printed totals could not be checked:{" "}
                    {period.printed_totals_error}
                  </p>
                )}
                {period.reason && <p>{period.reason}</p>}
                {period.amounts && (
                  <>
                    <dl className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                      {fields.map(([key, label]) => (
                        <div key={key}>
                          <dt className="text-sm text-muted-foreground">
                            {label}
                          </dt>
                          <dd className="font-mono">
                            {period.amounts![key] === null
                              ? "Unknown"
                              : correctionMoney(
                                  period.amounts![key]!,
                                  period.currency
                                )}
                          </dd>
                        </div>
                      ))}
                    </dl>
                    <p>
                      {period.counted_rows} admitted rows counted;{" "}
                      {period.excluded_rows} other rows excluded from this
                      arithmetic.
                    </p>
                    <p>
                      {period.independent
                        ? "Both balances are sourced from printed statement controls. Ledger signs reflect the recorded balance convention."
                        : "The balances do not provide an independent pair of printed controls."}
                    </p>
                  </>
                )}
                <StatementSourceButton
                  caseId={caseId}
                  periodId={period.period_id}
                  sourceDocumentId={period.source_document_id}
                />
                <StatementRunningBalances
                  caseId={caseId}
                  periodId={period.period_id}
                  sourceDocumentId={period.source_document_id}
                  currency={period.currency}
                />
                <details>
                  <summary>Recorded check and source details</summary>
                  <p>
                    Earlier stored check: {period.recorded_status}
                    {period.recorded_at
                      ? ` at ${period.recorded_at}`
                      : " (no recorded check time)"}
                    . This read has not overwritten it.
                  </p>
                  <p>
                    Opening balance source: {period.opening_source}; closing
                    balance source: {period.closing_source}.
                  </p>
                  <p className="break-all">
                    Source document: {period.source_document_id}
                  </p>
                </details>
              </article>
            ))}
            <div className="flex gap-2">
              <Button
                disabled={!offset || query.isFetching}
                onClick={() => setOffset((n) => Math.max(0, n - 25))}
              >
                Previous statement checks
              </Button>
              <Button
                disabled={!query.data.has_more || query.isFetching}
                onClick={() => setOffset((n) => n + 25)}
              >
                Next statement checks
              </Button>
            </div>
          </>
        ))}
    </section>
  )
}
