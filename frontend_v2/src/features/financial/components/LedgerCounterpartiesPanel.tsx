import { sha256Hex } from "@/lib/browser-crypto"
import { LinkedPayments } from "./LinkedPayments"
import { LedgerFlowChart } from "./LedgerFlowChart"
import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { z } from "zod"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import { assertCandidateScope, candidateUrl } from "../lib/candidate-contract"
import { formatLedgerAmount } from "../lib/ledger-format"
const correctionMoney = (value: string, currency: string) =>
  `${formatLedgerAmount(value, currency).text} ${currency}`
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
  has_credit_card_readings: z.boolean().default(false),
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
  autoLoad = false,
  identities = false,
}: {
  caseId: string
  params: LedgerQueryParams
  population?: "verified" | "working"
  autoLoad?: boolean
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
      autoLoad={autoLoad}
      identities={identities}
    />
  )
}
function CounterpartyScope({
  caseId,
  params,
  population = "verified",
  autoLoad = false,
  identities = false,
}: {
  caseId: string
  params: LedgerQueryParams
  population?: "verified" | "working"
  autoLoad?: boolean
  identities?: boolean
}) {
  const [opened, setOpened] = useState(autoLoad),
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
        const digest = await sha256Hex(
          new TextEncoder().encode(data.snapshot_json)
        )
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
      aria-label="People and businesses"
      className="space-y-2 rounded border p-3"
    >
      <h3 className="font-semibold">
        {population === "working" ? "Payments" : "Verified payments"} ·
        {identities
          ? "Names linked by an investigator"
          : "People and businesses"}
      </h3>
      <p>
        {identities
          ? "Payments you linked to the same person or business are shown together. Other names stay separate."
          : "See how much each name paid or received. Matching names are grouped together; check the statements before deciding that they refer to the same person or business."}{" "}
        Uses the account and dates selected above.
      </p>
      <Button
        variant="outline"
        disabled={query.isFetching}
        onClick={() => (opened ? void query.refetch() : setOpened(true))}
      >
        {opened ? "Refresh totals" : "Show totals"}
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
            <details className="text-sm">
              <summary className="cursor-pointer">
                How these totals were calculated
              </summary>
              <p>{query.data.limitation}</p>
            </details>
            <details className="text-sm">
              <summary className="cursor-pointer">
                How names were grouped
              </summary>
              <p>{query.data.counterparty_limitation}</p>
            </details>
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
                  {query.data.included_rows} payments included;{" "}
                  {query.data.excluded_rows} excluded. Open “How these totals
                  were calculated” for details.
                </p>
                <LedgerFlowChart
                  caseId={caseId}
                  hasCreditCards={query.data.has_credit_card_readings}
                  title={identities ? "Money by linked name" : "Money by name"}
                  groups={counterparties.map((p) => ({
                    ...p,
                    id: JSON.stringify([p.group_id ?? p.label, p.currency]),
                    label:
                      p.label === null
                        ? "Name not recorded"
                        : p.label === ""
                          ? "Name left blank"
                          : p.label.trim() === p.label
                            ? p.label
                            : JSON.stringify(p.label),
                  }))}
                  onSource={setSource}
                />
                {counterparties.length === 0 && (
                  <p>
                    No eligible payments for these filters. Evidence coverage
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
                      caseId={caseId}
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
  caseId,
}: {
  point: z.infer<typeof response>["counterparties"][number]
  caseId: string
}) {
  return (
    <div className="space-y-1 rounded border p-2">
      <p>
        {point.label === null
          ? "Name not recorded"
          : point.label === ""
            ? "Name left blank"
            : point.label}{" "}
        · {point.currency} · {point.rows} payments
      </p>
      <p>
        Credits: {correctionMoney(point.credits_minor, point.currency)} ·
        Debits: {correctionMoney(point.debits_minor, point.currency)} ·
        Difference: {correctionMoney(point.net_minor, point.currency)}
      </p>
      {point.raw_labels && (
        <p className="break-words">
          Names printed on statements:{" "}
          {point.raw_labels
            .map((label) =>
              label === null ? "Not recorded" : JSON.stringify(label)
            )
            .join(" · ")}
        </p>
      )}
      <LinkedPayments caseId={caseId} ids={point.transaction_ids} />
    </div>
  )
}
