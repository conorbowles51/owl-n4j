import { useQuery } from "@tanstack/react-query"
import { z } from "zod"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import { assertCandidateScope, candidateUrl } from "../lib/candidate-contract"
import { correctionMoney } from "../lib/correction-contract"
import type { LedgerQueryParams } from "../hooks/use-ledger-transactions"
const count = z.number().int().nonnegative()
const money = z.string().regex(/^-?(0|[1-9][0-9]*)$/)
const exclusions = z.object({
  quarantined: count,
  superseded: count,
  rejected: count,
  source_not_admitted: count,
  proof_class_not_included: count,
})
const common = z.object({
  case_id: z.string(),
  account_id: z.string().nullable(),
  start_date: z.string().nullable(),
  end_date: z.string().nullable(),
  included_classes: z.array(z.enum(["p0", "p1", "p2", "p3"])),
  max_rows: count.positive(),
  applied: z.literal(false),
  limitation: z.string(),
  population: z.literal("working").optional(),
  outside_verified_rows: count.nullable().optional(),
})
const report = z.discriminatedUnion("available", [
  common.extend({
    available: z.literal(false),
    reason: z.string(),
    considered_rows: z.null(),
    included_rows: z.null(),
    excluded_rows: z.null(),
    exclusions: z.null(),
    currencies: z.array(z.never()),
  }),
  common.extend({
    available: z.literal(true),
    reason: z.null(),
    considered_rows: count,
    included_rows: count,
    excluded_rows: count,
    exclusions,
    currencies: z.array(
      z.object({
        currency: z.string(),
        rows: count.positive(),
        credits_minor: money,
        debits_minor: money,
        net_minor: money,
      })
    ),
  }),
])
const labels = {
  quarantined: "Held-out rows",
  superseded: "Superseded readings",
  rejected: "Rejected readings",
  source_not_admitted: "Source excluded",
  proof_class_not_included: "Classification outside these totals",
}
export function LedgerSummaryPanel({
  caseId,
  params,
  population = "verified",
}: {
  caseId: string
  params: LedgerQueryParams
  population?: "verified" | "working"
}) {
  const working = population === "working"
  const account = params.accountId ?? null,
    start = params.startDate ?? null,
    end = params.endDate ?? null
  const query = useQuery({
    queryKey: [
      "financial-ledger",
      caseId,
      working ? "working-summary" : "summary",
      account,
      start,
      end,
    ],
    retry: false,
    queryFn: async () => {
      const search = new URLSearchParams()
      if (account) search.set("account_id", account)
      if (start) search.set("start_date", start)
      if (end) search.set("end_date", end)
      const data = report.parse(
        await fetchAPI<unknown>(
          `${candidateUrl(working ? "ledger-working-summary" : "ledger-summary", caseId)}&${search}`
        )
      )
      assertCandidateScope(data, caseId)
      if (
        working
          ? data.population !== "working" ||
            (data.available &&
              (data.outside_verified_rows == null ||
                data.outside_verified_rows > data.included_rows))
          : data.population !== undefined ||
            data.included_classes.includes("p3")
      )
        throw new Error("Summary returned for a different population.")
      if (
        data.account_id !== account ||
        data.start_date !== start ||
        data.end_date !== end
      )
        throw new Error("Summary returned for different filters.")
      if (
        data.available &&
        (data.considered_rows !== data.included_rows + data.excluded_rows ||
          Object.values(data.exclusions).reduce((a, b) => a + b, 0) !==
            data.excluded_rows ||
          data.currencies.reduce((a, g) => a + g.rows, 0) !==
            data.included_rows ||
          new Set(data.currencies.map((g) => g.currency)).size !==
            data.currencies.length ||
          data.currencies.some(
            (g) =>
              BigInt(g.credits_minor) < 0n ||
              BigInt(g.debits_minor) < 0n ||
              BigInt(g.credits_minor) - BigInt(g.debits_minor) !==
                BigInt(g.net_minor)
          ))
      )
        throw new Error("Summary counts or money disagree.")
      return data
    },
  })
  return (
    <section
      aria-label={working ? "Working ledger totals" : "Current ledger summary"}
      className="space-y-2 rounded border p-3"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-semibold">
          {working
            ? "Working totals — all current admitted readings"
            : "Verified totals"}
        </h3>
        <Button
          variant="outline"
          disabled={query.isFetching}
          onClick={() => void query.refetch()}
        >
          {working ? "Refresh working totals" : "Refresh ledger summary"}
        </Button>
      </div>
      <p className="text-muted-foreground">
        {account ? `Account ${account}` : "All ledger accounts"} ·{" "}
        {start ?? "Any start date"} to {end ?? "any end date"}
      </p>
      {working && (
        <p>
          Includes readings outside verified totals. Completeness remains
          unverified.
        </p>
      )}
      {query.isFetching || query.isPending ? (
        <p role="status">Calculating current ledger summary…</p>
      ) : query.isError ? (
        <p role="alert">Summary unavailable. {query.error.message}</p>
      ) : (
        <>
          <details>
            <summary>How these totals are calculated</summary>
            <p>{query.data.limitation}</p>
            <p>
              Included classifications:{" "}
              {query.data.included_classes
                .map((c) => c.toUpperCase())
                .join(", ")}
              .
            </p>
          </details>
          {working && query.data.available && (
            <p>
              {query.data.outside_verified_rows} of these rows remain outside
              verified totals.
            </p>
          )}
          {!query.data.available ? (
            <p>Summary unavailable. {query.data.reason}</p>
          ) : (
            <>
              <p>
                {query.data.included_rows} included rows;{" "}
                {query.data.excluded_rows} excluded from{" "}
                {query.data.considered_rows} rows in this scope.
              </p>
              {query.data.currencies.length === 0 && (
                <p>
                  No eligible postings in this scope. This does not establish
                  that no transactions occurred.
                </p>
              )}
              {query.data.currencies.map((group) => (
                <div
                  key={group.currency}
                  className="space-y-1 rounded border p-2"
                >
                  <p>
                    {group.currency} · {group.rows} included postings
                  </p>
                  <div className="grid gap-2 sm:grid-cols-3">
                    <p className="font-medium tabular-nums">
                      Credits:{" "}
                      {correctionMoney(group.credits_minor, group.currency)}
                    </p>
                    <p className="font-medium tabular-nums">
                      Debits:{" "}
                      {correctionMoney(group.debits_minor, group.currency)}
                    </p>
                    <p className="font-medium tabular-nums">
                      Net postings:{" "}
                      {correctionMoney(group.net_minor, group.currency)}
                    </p>
                  </div>
                </div>
              ))}
              <details>
                <summary>Excluded rows ({query.data.excluded_rows})</summary>
                <p>
                  Each row is counted once: row status first, then source
                  status, then classification.
                </p>
                {Object.entries(query.data.exclusions).map(([key, value]) => (
                  <p key={key}>
                    {labels[key as keyof typeof labels]}: {value}
                  </p>
                ))}
              </details>
            </>
          )}
        </>
      )}
    </section>
  )
}
