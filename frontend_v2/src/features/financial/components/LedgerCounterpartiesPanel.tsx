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
  label_basis: z.literal("counterparty_raw_exact"),
  counterparty_limitation: z.string(),
  available: z.boolean(),
  reason: z.string().nullable(),
  applied: z.literal(false),
  population: z.literal("working").optional(),
  limitation: z.string(),
  included_rows: count.nullable(),
  excluded_rows: count.nullable(),
  currencies: z.array(totals),
  counterparties: z.array(
    totals.extend({
      label: z.string().nullable(),
      transaction_ids: z.array(z.string()),
      source_document_ids: z.array(z.string()),
    })
  ),
})
export function LedgerCounterpartiesPanel({
  caseId,
  params,
  population = "verified",
}: {
  caseId: string
  params: LedgerQueryParams
  population?: "verified" | "working"
}) {
  return (
    <CounterpartyScope
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
    />
  )
}
function CounterpartyScope({
  caseId,
  params,
  population = "verified",
}: {
  caseId: string
  params: LedgerQueryParams
  population?: "verified" | "working"
}) {
  const [opened, setOpened] = useState(false),
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
      "counterparties",
      account,
      start,
      end,
    ],
    enabled: opened,
    retry: false,
    queryFn: async () => {
      const search = new URLSearchParams(
        population === "working" ? { grouping: "counterparty" } : {}
      )
      if (account) search.set("account_id", account)
      if (start) search.set("start_date", start)
      if (end) search.set("end_date", end)
      const data = response.parse(
        await fetchAPI<unknown>(
          `${candidateUrl(population === "working" ? "ledger-working-analysis" : "ledger-counterparties", caseId)}&${search}`
        )
      )
      assertCandidateScope(data, caseId)
      if ((population === "working") !== (data.population === "working"))
        throw new Error("Analysis returned for a different population.")
      if (
        data.account_id !== account ||
        data.start_date !== start ||
        data.end_date !== end
      )
        throw new Error("Counterparty totals returned for different filters.")
      if (!data.available) {
        if (
          data.counterparties.length ||
          data.currencies.length ||
          data.included_rows !== null ||
          data.excluded_rows !== null
        )
          throw new Error(
            "Unavailable counterparty totals contained partial results."
          )
        return data
      }
      const ids = new Set<string>(),
        keys = new Set<string>()
      for (const point of data.counterparties) {
        const key = JSON.stringify([point.label, point.currency])
        if (
          !point.source_document_ids.length ||
          new Set(point.source_document_ids).size !==
            point.source_document_ids.length ||
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
          throw new Error("Counterparty money totals disagree.")
      }
      if (
        data.excluded_rows === null ||
        ids.size !== data.included_rows ||
        new Set(data.currencies.map((g) => g.currency)).size !==
          data.currencies.length ||
        data.counterparties.some(
          (p) => !data.currencies.some((g) => g.currency === p.currency)
        )
      )
        throw new Error("Counterparty counts disagree.")
      for (const group of data.currencies) {
        const counterparties = data.counterparties.filter(
          (p) => p.currency === group.currency
        )
        if (counterparties.reduce((n, p) => n + p.rows, 0) !== group.rows)
          throw new Error("Counterparty row totals disagree.")
        for (const field of [
          "credits_minor",
          "debits_minor",
          "net_minor",
        ] as const)
          if (
            counterparties.reduce((n, p) => n + BigInt(p[field]), 0n) !==
            BigInt(group[field])
          )
            throw new Error(
              "Counterparty totals do not match the ledger summary."
            )
      }
      return data
    },
  })
  const counterparties = query.data?.counterparties ?? [],
    safePage = Math.min(
      page,
      Math.max(0, Math.ceil(counterparties.length / 25) - 1)
    )
  return (
    <section
      aria-label="Ledger counterparty labels"
      className="space-y-2 rounded border p-3"
    >
      <h3 className="font-semibold">
        {population === "working" ? "Working analysis" : "Verified analysis"} ·
        Ledger counterparty labels
      </h3>
      <p>
        Groups source labels exactly as recorded, separately by currency. Equal
        labels do not establish identity or transfer matches. Missing and blank
        labels remain explicit. Uses the applied account and ordering-date
        filters.
      </p>
      <Button
        variant="outline"
        disabled={query.isFetching}
        onClick={() => (opened ? void query.refetch() : setOpened(true))}
      >
        {opened
          ? "Refresh ledger counterparty totals"
          : "Read ledger counterparty totals"}
      </Button>
      {opened &&
        (query.isFetching || query.isPending ? (
          <p role="status">Reading counterparty totals…</p>
        ) : query.isError ? (
          <p role="alert">
            Counterparty totals unavailable. {query.error.message}
          </p>
        ) : (
          <>
            <p>{query.data.limitation}</p>
            <p>{query.data.counterparty_limitation}</p>
            {!query.data.available ? (
              <p>Counterparty totals unavailable. {query.data.reason}</p>
            ) : (
              <>
                <p>
                  {query.data.included_rows} included postings;{" "}
                  {query.data.excluded_rows} excluded. See Current ledger
                  summary for exclusion reasons.
                </p>
                {counterparties.length === 0 && (
                  <p>
                    No eligible postings for these filters. Evidence coverage
                    may still be incomplete.
                  </p>
                )}
                {counterparties
                  .slice(safePage * 25, safePage * 25 + 25)
                  .map((point) => (
                    <Point
                      key={JSON.stringify([point.label, point.currency])}
                      point={point}
                      onSource={setSource}
                    />
                  ))}
                <Button
                  variant="outline"
                  disabled={safePage === 0}
                  onClick={() => setPage(safePage - 1)}
                >
                  Previous counterparty totals
                </Button>
                <Button
                  variant="outline"
                  disabled={(safePage + 1) * 25 >= counterparties.length}
                  onClick={() => setPage(safePage + 1)}
                >
                  Next counterparty totals
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
  point: z.infer<typeof response>["counterparties"][number]
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
        {point.label === null
          ? "Counterparty not recorded"
          : point.label === ""
            ? "Blank source label"
            : JSON.stringify(point.label)}{" "}
        · {point.currency} · {point.rows} postings
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
