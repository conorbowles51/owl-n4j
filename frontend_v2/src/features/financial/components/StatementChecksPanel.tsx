import { currentNativeControls } from "../lib/native-control-contract"
import { NativeControlComparisonPanel } from "./NativeControlComparisonPanel"
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
import { formatLedgerAmount } from "../lib/ledger-format"

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
    filename: z.string().nullable().optional(),
    balance_convention: z
      .enum(["asset_balance", "liability_owed"])
      .nullable()
      .optional(),
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
    zero_amount_rows: count.nullable().optional(),
    excluded_rows: count.nullable(),
    independent: z.boolean().nullable(),
    native_controls: currentNativeControls.nullable().optional(),
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
    if (v.zero_amount_rows != null && v.zero_amount_rows > v.counted_rows)
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
  account_id: z.string().nullable().optional(),
  offset: count,
  has_more: z.boolean(),
  applied: z.literal(false),
  checked_at: z.string(),
  native_controls_requested: z.boolean().default(false),
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

function balanceSummary(value: string, currency: string) {
  const formatted = formatLedgerAmount(value, currency)
  return formatted.scaled
    ? `${formatted.text} ${formatted.currency}`
    : correctionMoney(value, currency)
}

export function StatementChecksPanel({
  caseId,
  autoLoad = false,
  accountId,
  onOpenTransactions,
}: {
  caseId: string | undefined
  autoLoad?: boolean
  accountId?: string
  onOpenTransactions?: (start?: string, end?: string) => void
}) {
  const [opened, setOpened] = useState(autoLoad),
    [offset, setOffset] = useState(0),
    [includeNative, setIncludeNative] = useState(false)
  const query = useQuery({
    queryKey: [
      "financial-ledger",
      caseId,
      "statement-checks",
      accountId,
      offset,
      includeNative,
    ],
    enabled: opened && Boolean(caseId),
    retry: false,
    queryFn: async () => {
      const data = report.parse(
        await fetchAPI<unknown>(
          `${candidateUrl("statement-checks", caseId!)}&offset=${offset}&include_native=${includeNative}${accountId ? `&account_id=${encodeURIComponent(accountId)}` : ""}`
        )
      )
      assertCandidateScope(data, caseId!)
      if (
        accountId &&
        (data.account_id !== accountId ||
          data.items.some((period) => period.account_id !== accountId))
      )
        throw new Error(
          "Statements returned for a different account. Reload the check."
        )
      if (
        data.offset !== offset ||
        data.native_controls_requested !== includeNative
      )
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
        Compare each statement’s recorded balances with its imported payments.
        Open the statement to investigate a difference or a missing balance.
      </p>
      <Button
        variant="outline"
        disabled={query.isFetching}
        onClick={() => (opened ? void query.refetch() : setOpened(true))}
      >
        {opened ? "Refresh balance checks" : "Check statement balances"}
      </Button>
      {opened && (
        <details className="text-sm">
          <summary className="cursor-pointer">Additional file checks</summary>
          <label className="block">
            <input
              aria-label="Recheck native bank-file controls"
              type="checkbox"
              checked={includeNative}
              onChange={(e) => setIncludeNative(e.target.checked)}
            />{" "}
            Recheck native bank-file controls against current readings (reads
            original files)
          </label>
        </details>
      )}
      {opened &&
        (query.isPending ? (
          <p role="status">Checking current statement balances…</p>
        ) : query.isError ? (
          <p role="alert">Balance checks unavailable. {query.error.message}</p>
        ) : (
          <>
            <details className="text-sm space-y-2">
              <summary className="cursor-pointer">
                Save these check results and read calculation details
              </summary>
              <Button
                variant="outline"
                disabled={query.isFetching}
                onClick={() => {
                  const url = URL.createObjectURL(
                    new Blob(
                      [
                        JSON.stringify(
                          {
                            schema: "loupe.financial.statement_checks/1",
                            ...query.data,
                          },
                          null,
                          2
                        ),
                      ],
                      { type: "application/json" }
                    )
                  )
                  const link = document.createElement("a")
                  link.href = url
                  link.download = `loupe-statement-checks-page-${Math.floor(offset / 25) + 1}.json`
                  link.click()
                  setTimeout(() => URL.revokeObjectURL(url), 1000)
                }}
              >
                Download this page of statement checks
              </Button>
              <p className="text-sm">
                The download captures these displayed periods only, including
                any requested whole-source native checks. Other statement pages
                and source files are not included.
              </p>
              <p className="text-sm">
                Checked at {query.data.checked_at}. {query.data.limitation}
              </p>
            </details>
            {query.data.items.length === 0 && (
              <p>
                No imported statement periods were found here. Upload and
                confirm a statement to record its dates and balances.
              </p>
            )}
            <div
              className="max-h-[38rem] space-y-3 overflow-auto"
              aria-label="Statements and balances"
            >
              {query.data.items.map((period) => (
                <article
                  key={period.period_id}
                  className="space-y-3 rounded border p-3"
                >
                  <div className="flex flex-wrap justify-between gap-2">
                    <h4 className="font-semibold break-words">
                      {period.filename || period.account_label} ·{" "}
                      {period.currency}
                    </h4>
                    <strong
                      className={`rounded px-2 py-1 text-sm ${period.status === "balanced" ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300" : "bg-amber-500/10 text-amber-800 dark:text-amber-300"}`}
                    >
                      {statusLabel[period.status]}
                    </strong>
                  </div>
                  <p>
                    {period.start ?? "Unknown start"} to{" "}
                    {period.end ?? "unknown end"}
                  </p>
                  {period.source_status !== "admitted" && (
                    <p className="text-sm text-amber-700 dark:text-amber-300">
                      This statement is excluded from current transaction
                      totals.
                    </p>
                  )}
                  {period.amounts && (
                    <dl className="grid gap-3 sm:grid-cols-3">
                      {(["opening", "closing", "difference"] as const).map(
                        (field) => {
                          const owed =
                            period.balance_convention === "liability_owed"
                          const value = period.amounts![field]
                          return (
                            <div key={field}>
                              <dt className="text-sm text-muted-foreground">
                                {field === "opening"
                                  ? owed
                                    ? "Opening amount owed"
                                    : "Opening balance"
                                  : field === "closing"
                                    ? owed
                                      ? "Closing amount owed"
                                      : "Closing balance"
                                    : "Difference"}
                              </dt>
                              <dd className="font-semibold tabular-nums">
                                {value === null
                                  ? "Not available"
                                  : balanceSummary(
                                      owed && field !== "difference"
                                        ? String(-BigInt(value))
                                        : field === "difference"
                                          ? String(
                                              BigInt(value) < 0n
                                                ? -BigInt(value)
                                                : BigInt(value)
                                            )
                                          : value,
                                      period.currency
                                    )}
                              </dd>
                            </div>
                          )
                        }
                      )}
                    </dl>
                  )}
                  {period.status === "unavailable" && (
                    <p className="text-sm">
                      {period.amounts?.opening === null &&
                        "Opening balance not recorded. "}
                      {period.amounts?.closing === null &&
                        "Closing balance not recorded. "}
                      Open the statement to check whether these values are
                      printed.
                    </p>
                  )}
                  {period.status === "balanced" && (
                    <p className="text-sm">
                      The imported payments agree with the recorded balances.
                    </p>
                  )}
                  {period.status === "unbalanced" && (
                    <p className="text-sm">
                      Check the original statement and its payments for a
                      missing or incorrect value.
                    </p>
                  )}
                  {period.status === "refused" && (
                    <p role="alert">{period.reason}</p>
                  )}
                  {period.amounts && (
                    <p className="text-sm text-muted-foreground">
                      {period.counted_rows} imported{" "}
                      {period.counted_rows === 1 ? "entry" : "entries"} in this
                      check · {period.excluded_rows} excluded{" "}
                      {period.excluded_rows === 1 ? "entry" : "entries"}
                    </p>
                  )}
                  <div className="flex flex-wrap gap-2">
                    <StatementSourceButton
                      caseId={caseId}
                      periodId={period.period_id}
                      sourceDocumentId={period.source_document_id}
                      label="Open statement and balances"
                    />
                    {onOpenTransactions && (
                      <Button
                        variant="outline"
                        onClick={() =>
                          onOpenTransactions(
                            period.start ?? undefined,
                            period.end ?? undefined
                          )
                        }
                      >
                        {period.start && period.end
                          ? "View transactions for these dates"
                          : "View account transactions"}
                      </Button>
                    )}
                  </div>
                  <details className="space-y-3 text-sm">
                    <summary className="cursor-pointer">
                      Calculation and further checks
                    </summary>
                    <p>
                      Source: {period.source_status} ·{" "}
                      {period.proof_class.toUpperCase()}. These checks do not
                      change source eligibility.
                    </p>
                    {period.delta_hints && (
                      <StatementDeltaHintsPanel
                        key={`${query.data.checked_at}:${period.period_id}`}
                        caseId={caseId}
                        currency={period.currency}
                        hints={period.delta_hints}
                      />
                    )}
                    {period.native_controls && (
                      <NativeControlComparisonPanel
                        comparison={period.native_controls}
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
                    {period.reason && period.status !== "refused" && (
                      <p>{period.reason}</p>
                    )}
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
                        {period.zero_amount_rows != null &&
                          period.zero_amount_rows > 0 && (
                            <p>
                              Includes {period.zero_amount_rows} zero-amount
                              readings; these preserve printed lines and are not
                              nonzero payments.
                            </p>
                          )}
                        <p>
                          {period.independent
                            ? "Both balances are sourced from printed statement controls. Ledger signs reflect the recorded balance convention."
                            : "The balances do not provide an independent pair of printed controls."}
                        </p>
                      </>
                    )}
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
                  </details>
                </article>
              ))}
            </div>
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
