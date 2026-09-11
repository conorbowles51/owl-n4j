import { LedgerFlowChart } from "./LedgerFlowChart"
import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { z } from "zod"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import { assertCandidateScope, candidateUrl } from "../lib/candidate-contract"
import { correctionMoney } from "../lib/correction-contract"
import type { LedgerQueryParams } from "../hooks/use-ledger-transactions"
import { LedgerSourceDialog } from "./LedgerSourceDialog"
const count = z.number().int().nonnegative(),
  money = z.string().regex(/^-?(0|[1-9][0-9]*)$/)
const totals = z.object({
  currency: z.string(),
  rows: count.positive(),
  credits_minor: money,
  debits_minor: money,
  net_minor: money,
})
const response = z.object({
  case_id: z.string(),
  account_id: z.string().nullable(),
  start_date: z.string().nullable(),
  end_date: z.string().nullable(),
  grouping: z.enum(["daily", "monthly"]),
  date_basis: z.literal("ordering_date"),
  available: z.boolean(),
  reason: z.string().nullable(),
  applied: z.literal(false),
  population: z.literal("working").optional(),
  limitation: z.string(),
  included_rows: count.nullable(),
  excluded_rows: count.nullable(),
  currencies: z.array(totals),
  points: z.array(
    totals.extend({
      date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
      transaction_ids: z.array(z.string()),
      source_document_ids: z.array(z.string()),
    })
  ),
})
export function LedgerTrendsPanel({
  caseId,
  params,
  population = "verified",
  autoLoad = false,
}: {
  caseId: string
  params: LedgerQueryParams
  population?: "verified" | "working"
  autoLoad?: boolean
}) {
  return (
    <TrendScope
      key={JSON.stringify([
        caseId,
        population,
        params.accountId,
        params.startDate,
        params.endDate,
      ])}
      caseId={caseId}
      params={params}
      population={population}
      autoLoad={autoLoad}
    />
  )
}
function TrendScope({
  caseId,
  params,
  population = "verified",
  autoLoad = false,
}: {
  caseId: string
  params: LedgerQueryParams
  population?: "verified" | "working"
  autoLoad?: boolean
}) {
  const [grouping, setGrouping] = useState<"daily" | "monthly">("monthly"),
    [opened, setOpened] = useState(autoLoad),
    [page, setPage] = useState(0)
  const [source, setSource] = useState<string | null>(null)
  const account = params.accountId ?? null,
    start = params.startDate ?? null,
    end = params.endDate ?? null
  const query = useQuery({
    queryKey: [
      "financial-ledger",
      caseId,
      population,
      "trends",
      account,
      start,
      end,
      grouping,
    ],
    enabled: opened,
    retry: false,
    queryFn: async () => {
      const search = new URLSearchParams({ grouping })
      if (account) search.set("account_id", account)
      if (start) search.set("start_date", start)
      if (end) search.set("end_date", end)
      const data = response.parse(
        await fetchAPI<unknown>(
          `${candidateUrl(population === "working" ? "ledger-working-analysis" : "ledger-trends", caseId)}&${search}`
        )
      )
      assertCandidateScope(data, caseId)
      if ((population === "working") !== (data.population === "working"))
        throw new Error("Analysis returned for a different population.")
      if (
        data.account_id !== account ||
        data.start_date !== start ||
        data.end_date !== end ||
        data.grouping !== grouping
      )
        throw new Error("Date totals returned for different filters.")
      if (!data.available) {
        if (
          data.points.length ||
          data.currencies.length ||
          data.included_rows !== null
        )
          throw new Error("Unavailable date totals contained partial results.")
        return data
      }
      const ids = new Set<string>(),
        keys = new Set<string>()
      for (const point of data.points) {
        const key = `${point.date}:${point.currency}`
        if (
          keys.has(key) ||
          point.rows !== point.transaction_ids.length ||
          point.transaction_ids.some((id) => ids.has(id)) ||
          new Set(point.transaction_ids).size !== point.rows
        )
          throw new Error("Contributing readings are inconsistent.")
        keys.add(key)
        point.transaction_ids.forEach((id) => ids.add(id))
        if (
          BigInt(point.credits_minor) < 0n ||
          BigInt(point.debits_minor) < 0n ||
          BigInt(point.credits_minor) - BigInt(point.debits_minor) !==
            BigInt(point.net_minor)
        )
          throw new Error("Date money totals disagree.")
      }
      if (
        ids.size !== data.included_rows ||
        new Set(data.currencies.map((g) => g.currency)).size !==
          data.currencies.length ||
        data.points.some(
          (p) => !data.currencies.some((g) => g.currency === p.currency)
        )
      )
        throw new Error("Date counts disagree.")
      for (const group of data.currencies) {
        const points = data.points.filter((p) => p.currency === group.currency)
        if (points.reduce((n, p) => n + p.rows, 0) !== group.rows)
          throw new Error("Date row totals disagree.")
        for (const field of [
          "credits_minor",
          "debits_minor",
          "net_minor",
        ] as const)
          if (
            points.reduce((n, p) => n + BigInt(p[field]), 0n) !==
            BigInt(group[field])
          )
            throw new Error("Date totals do not match the ledger summary.")
      }
      return data
    },
  })
  const points = query.data?.points ?? [],
    safePage = Math.min(page, Math.max(0, Math.ceil(points.length / 25) - 1))
  return (
    <section
      aria-label="Ledger totals by date"
      className="space-y-2 rounded border p-3"
    >
      <h3 className="font-semibold">
        {population === "working" ? "Working analysis" : "Verified analysis"} ·
        Ledger totals by date
      </h3>
      <p>
        Uses the applied account/date filters and ledger ordering dates. Missing
        dates are not evidence of no activity. Monthly dates label the start of
        each month.
      </p>
      <label>
        Group ledger dates
        <select
          className="ml-2 rounded border p-2"
          value={grouping}
          onChange={(e) => {
            setGrouping(e.target.value as "daily" | "monthly")
            setPage(0)
            setSource(null)
          }}
        >
          <option value="monthly">Monthly</option>
          <option value="daily">Daily</option>
        </select>
      </label>
      <Button
        variant="outline"
        disabled={query.isFetching}
        onClick={() => (opened ? void query.refetch() : setOpened(true))}
      >
        {opened ? "Refresh ledger date totals" : "Read ledger date totals"}
      </Button>
      {opened &&
        (query.isFetching || query.isPending ? (
          <p role="status">Reading date totals…</p>
        ) : query.isError ? (
          <p role="alert">Date totals unavailable. {query.error.message}</p>
        ) : (
          <>
            <p>{query.data.limitation}</p>
            {!query.data.available ? (
              <p>Date totals unavailable. {query.data.reason}</p>
            ) : (
              <>
                <p>
                  {query.data.included_rows} included postings;{" "}
                  {query.data.excluded_rows} excluded. See Current ledger
                  summary for exclusion reasons.
                </p>
                <LedgerFlowChart
                  title="Money by ordering date"
                  groups={points.map((p) => ({
                    ...p,
                    id: `${p.date}:${p.currency}`,
                    label:
                      grouping === "monthly"
                        ? `${p.date.slice(0, 7)} (month)`
                        : p.date,
                  }))}
                  onSource={setSource}
                />
                {points.length === 0 && (
                  <p>
                    No eligible postings for these dates. Evidence coverage may
                    still be incomplete.
                  </p>
                )}
                {points
                  .slice(safePage * 25, safePage * 25 + 25)
                  .map((point) => (
                    <Point
                      key={`${grouping}:${point.date}:${point.currency}`}
                      point={point}
                      onSource={setSource}
                    />
                  ))}
                <Button
                  variant="outline"
                  disabled={safePage === 0}
                  onClick={() => setPage(safePage - 1)}
                >
                  Previous date totals
                </Button>
                <Button
                  variant="outline"
                  disabled={(safePage + 1) * 25 >= points.length}
                  onClick={() => setPage(safePage + 1)}
                >
                  Next date totals
                </Button>
              </>
            )}
          </>
        ))}
      {source && (
        <LedgerSourceDialog
          key={source}
          caseId={caseId}
          transactionId={source}
          onClose={() => setSource(null)}
        />
      )}
    </section>
  )
}
function Point({
  point,
  onSource,
}: {
  point: z.infer<typeof response>["points"][number]
  onSource: (id: string) => void
}) {
  const [page, setPage] = useState(0),
    safePage = Math.min(
      page,
      Math.max(0, Math.ceil(point.transaction_ids.length / 25) - 1)
    )
  return (
    <div className="space-y-1 rounded border p-2">
      <p>
        {point.date} · {point.currency} · {point.rows} postings
      </p>
      <p>
        Credits: {correctionMoney(point.credits_minor, point.currency)} ·
        Debits: {correctionMoney(point.debits_minor, point.currency)} · Net
        postings: {correctionMoney(point.net_minor, point.currency)}
      </p>
      <details>
        <summary>Contributing readings ({point.rows})</summary>
        <p>
          {point.source_document_ids.length} source documents. Each link opens
          the recorded source for that contributing reading.
        </p>
        {point.transaction_ids
          .slice(safePage * 25, safePage * 25 + 25)
          .map((id, index) => (
            <Button key={id} variant="outline" onClick={() => onSource(id)}>
              Open contributing reading {safePage * 25 + index + 1}
            </Button>
          ))}
        <Button
          variant="outline"
          disabled={safePage === 0}
          onClick={() => setPage(safePage - 1)}
        >
          Previous contributing readings
        </Button>
        <Button
          variant="outline"
          disabled={(safePage + 1) * 25 >= point.rows}
          onClick={() => setPage(safePage + 1)}
        >
          Next contributing readings
        </Button>
      </details>
    </div>
  )
}
