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
  label_basis: z.enum([
    "counterparty_raw_exact",
    "investigator_payment_identity",
  ]),
  snapshot_sha256: z.string().optional(),
  snapshot_json: z.string().optional(),
  counterparty_limitation: z.string(),
  available: z.boolean(),
  reason: z.string().nullable(),
  applied: z.literal(false),
  population: z.enum(["working", "verified"]).optional(),
  limitation: z.string(),
  included_rows: count.nullable(),
  excluded_rows: count.nullable(),
  currencies: z.array(totals),
  counterparties: z.array(
    totals.extend({
      label: z.string().nullable(),
      group_id: z.string().optional(),
      party: z
        .object({ id: z.string().uuid(), name: z.string() })
        .nullable()
        .optional(),
      raw_labels: z.array(z.string().nullable()).optional(),
      transaction_ids: z.array(z.string()),
      source_document_ids: z.array(z.string()),
    })
  ),
})
export function LedgerCounterpartiesPanel({
  caseId,
  params,
  population = "verified",
  identities = false,
}: {
  caseId: string
  params: LedgerQueryParams
  population?: "verified" | "working"
  identities?: boolean
}) {
  return (
    <CounterpartyScope
      key={JSON.stringify([
        caseId,
        population,
        identities,
        params.accountId,
        params.startDate,
        params.endDate,
      ])}
      caseId={caseId}
      params={params}
      population={population}
      identities={identities}
    />
  )
}
function CounterpartyScope({
  caseId,
  params,
  population = "verified",
  identities = false,
}: {
  caseId: string
  params: LedgerQueryParams
  population?: "verified" | "working"
  identities?: boolean
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
      identities,
      account,
      start,
      end,
    ],
    enabled: opened,
    retry: false,
    queryFn: async () => {
      const search = new URLSearchParams(
        identities
          ? { population }
          : population === "working"
            ? { grouping: "counterparty" }
            : {}
      )
      if (account) search.set("account_id", account)
      if (start) search.set("start_date", start)
      if (end) search.set("end_date", end)
      const data = response.parse(
        await fetchAPI<unknown>(
          `${candidateUrl(identities ? "counterparty-party-analysis" : population === "working" ? "ledger-working-analysis" : "ledger-counterparties", caseId)}&${search}`
        )
      )
      assertCandidateScope(data, caseId)
      if (
        data.label_basis !==
        (identities
          ? "investigator_payment_identity"
          : "counterparty_raw_exact")
      )
        throw Error("Analysis returned a different grouping basis.")
      if (identities) {
        if (
          !data.snapshot_json ||
          !data.snapshot_sha256 ||
          data.counterparties.some((p) => !p.group_id)
        )
          throw Error("Identity analysis is missing its captured source.")
        const digest = Array.from(
          new Uint8Array(
            await crypto.subtle.digest(
              "SHA-256",
              new TextEncoder().encode(data.snapshot_json)
            )
          ),
          (b) => b.toString(16).padStart(2, "0")
        ).join("")
        if (digest !== data.snapshot_sha256)
          throw Error("Identity source capture hash differs.")
        const ledger = JSON.parse(data.snapshot_json).ledger
        if (
          ledger.case_id !== caseId ||
          ledger.account_id !== account ||
          ledger.start_date !== start ||
          ledger.end_date !== end
        )
          throw Error("Identity capture belongs to a different scope.")
      }

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
        const key = JSON.stringify([
          point.group_id ?? point.label,
          point.currency,
        ])
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
        {identities
          ? "Reviewed counterparty identities"
          : "Ledger counterparty labels"}
      </h3>
      <p>
        {identities
          ? "Groups only explicitly linked payments by reviewed identity; other labels remain unresolved. Identity decisions do not match transfers or change eligibility."
          : "Groups source labels exactly as recorded, separately by currency. Equal labels do not establish identity or transfer matches. Missing and blank labels remain explicit."}{" "}
        Uses the applied account and ordering-date filters.
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
            {identities && (
              <Button
                variant="outline"
                onClick={() => {
                  const url = URL.createObjectURL(
                    new Blob([JSON.stringify(query.data, null, 2)], {
                      type: "application/json",
                    })
                  )
                  const link = document.createElement("a")
                  link.href = url
                  link.download = "loupe-reviewed-counterparties.json"
                  link.click()
                  setTimeout(() => URL.revokeObjectURL(url), 1000)
                }}
              >
                Download reviewed counterparty analysis
              </Button>
            )}

            {!query.data.available ? (
              <p>Counterparty totals unavailable. {query.data.reason}</p>
            ) : (
              <>
                <p>
                  {query.data.included_rows} included postings;{" "}
                  {query.data.excluded_rows} excluded. See Current ledger
                  summary for exclusion reasons.
                </p>
                <LedgerFlowChart
                  title={
                    identities
                      ? "Money by reviewed counterparty"
                      : "Money by source label"
                  }
                  groups={counterparties.map((p) => ({
                    ...p,
                    id: JSON.stringify([p.group_id ?? p.label, p.currency]),
                    label:
                      p.label === null
                        ? "Counterparty not recorded"
                        : p.label === ""
                          ? "Blank source label"
                          : p.label.trim() === p.label
                            ? p.label
                            : JSON.stringify(p.label),
                  }))}
                  onSource={setSource}
                />
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
                      key={JSON.stringify([
                        point.group_id ?? point.label,
                        point.currency,
                      ])}
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
      {point.raw_labels && (
        <p className="break-words">
          Original source labels:{" "}
          {point.raw_labels
            .map((label) =>
              label === null ? "Not recorded" : JSON.stringify(label)
            )
            .join(" · ")}
        </p>
      )}
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
