import { useState } from "react"
import { useMutation } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import { timelineAPI } from "@/features/timeline/api"
import { useGraphStore } from "@/stores/graph.store"
import { useUIStore } from "@/stores/ui.store"
import { candidateUrl } from "../lib/candidate-contract"
import {
  ledgerTimeline,
  chronologyLabels,
  validContextDate,
  type LedgerTimeline,
} from "../lib/ledger-timeline"
import { correctionMoney } from "../lib/correction-contract"
import { LedgerFilters } from "./LedgerFilters"
import { RequestedCoveragePanel } from "./RequestedCoveragePanel"
import { LedgerSourceDialog } from "./LedgerSourceDialog"
import type { LedgerQueryParams } from "../hooks/use-ledger-transactions"
import type { TimelineResponse } from "@/features/timeline/api"

export function FinancialCaseTimeline({
  caseId,
}: {
  caseId: string | undefined
}) {
  const [params, setParams] = useState<LedgerQueryParams>({}),
    [population, setPopulation] = useState("working")
  if (!caseId) return <p>Choose a case for its financial timeline.</p>
  return (
    <section aria-label="Financial case timeline" className="space-y-4 p-4">
      <h2 className="font-semibold">Payments in case context</h2>
      <p>
        Read current ledger postings beside case events. Date proximity is a
        review aid; it does not establish that an event explains or corroborates
        a payment.
      </p>
      <LedgerFilters caseId={caseId} onApply={setParams} />
      <RequestedCoveragePanel caseId={caseId} params={params} />
      <label>
        Timeline population{" "}
        <select
          aria-label="Timeline population"
          className="border bg-background p-2"
          value={population}
          onChange={(e) => setPopulation(e.target.value)}
        >
          <option value="working">Working readings, including P3</option>
          <option value="verified">Verified only</option>
        </select>
      </label>
      <TimelineScope
        key={JSON.stringify([caseId, params, population])}
        caseId={caseId}
        params={params}
        population={population}
      />
    </section>
  )
}
function TimelineScope({
  caseId,
  params,
  population,
}: {
  caseId: string
  params: LedgerQueryParams
  population: string
}) {
  const [source, setSource] = useState<string | null>(null),
    [search, setSearch] = useState(""),
    [page, setPage] = useState(0),
    [kind, setKind] = useState("both")
  const selectNodes = useGraphStore((s) => s.selectNodes),
    expand = useUIStore((s) => s.expandGraphPanelTo)
  const load = useMutation({
    retry: false,
    mutationFn: async () => {
      const query = new URLSearchParams({ population })
      if (params.accountId) query.set("account_id", params.accountId)
      if (params.startDate) query.set("start_date", params.startDate)
      if (params.endDate) query.set("end_date", params.endDate)
      const [ledgerResult, eventResult] = await Promise.allSettled([
        fetchAPI(`${candidateUrl("ledger-timeline", caseId)}&${query}`, {
          timeout: 120000,
        }),
        timelineAPI.getEvents({
          caseId,
          startDate: params.startDate,
          endDate: params.endDate,
          limit: 2000,
          scope: "all",
        }),
      ])
      if (ledgerResult.status === "rejected") throw ledgerResult.reason
      const ledger = ledgerTimeline.parse(ledgerResult.value)
      if (
        ledger.case_id !== caseId ||
        ledger.account_id !== (params.accountId ?? null) ||
        ledger.start_date !== (params.startDate ?? null) ||
        ledger.end_date !== (params.endDate ?? null) ||
        ledger.population !== population
      )
        throw Error("Timeline returned a different ledger scope.")
      return {
        ledger,
        events: eventResult.status === "fulfilled" ? eventResult.value : null,
        eventsError: eventResult.status === "rejected",
        capturedAt: new Date().toISOString(),
      }
    },
  })
  const data = load.data
  type Item =
    | {
        key: string
        date: string
        kind: "posting"
        row: LedgerTimeline["rows"][number]
      }
    | {
        key: string
        date: string
        kind: "event"
        event: TimelineResponse["events"][number]
      }
  const all: Item[] = data
    ? [
        ...data.ledger.rows.map((row) => ({
          key: "posting:" + row.key,
          date: row.chronology_date,
          kind: "posting" as const,
          row,
        })),
        ...(data.events?.events ?? [])
          .filter((e) => validContextDate(e.date))
          .map((event) => ({
            key: "event:" + event.key,
            date: event.date.slice(0, 10),
            kind: "event" as const,
            event,
          })),
      ].sort(
        (a, b) => a.date.localeCompare(b.date) || a.key.localeCompare(b.key)
      )
    : []
  const visible = all.filter(
    (item) =>
      (kind === "both" || kind === item.kind) &&
      JSON.stringify(item.kind === "posting" ? item.row : item.event)
        .toLowerCase()
        .includes(search.trim().toLowerCase())
  )
  const download = () => {
    if (!data) return
    const payload = {
      schema: "loupe.financial.case_timeline/1",
      case_id: caseId,
      scope: params,
      population,
      captured_at: data.capturedAt,
      ledger: data.ledger,
      case_events: data.events,
      case_events_unavailable: data.eventsError,
      display: { search, kind },
      limitation:
        "Ledger and graph responses were fetched separately, not in one cross-database snapshot. Case events never contribute ledger amounts or prove a correlation.",
    }
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" })
    )
    const a = document.createElement("a")
    a.href = url
    a.download = "loupe-financial-case-timeline.json"
    a.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  return (
    <div className="space-y-4">
      <Button
        disabled={load.isPending}
        onClick={() => {
          setPage(0)
          load.mutate()
        }}
      >
        {load.isPending ? "Loading…" : "Load payments and case events"}
      </Button>
      {load.isError && <p role="alert">{load.error.message}</p>}
      {data && (
        <>
          <p>{data.ledger.limitation}</p>
          <p>
            {data.ledger.rows.length} current ledger postings;{" "}
            {data.ledger.excluded_rows} excluded readings. Case events are shown
            for the case and selected dates, independently of the selected
            ledger account.
          </p>
          {data.eventsError ? (
            <p role="alert">
              Case events could not be loaded. The ledger remains available;
              this is not an empty case-event result.
            </p>
          ) : (
            <p>
              {data.events?.events.length ?? 0} of {data.events?.total ?? 0}{" "}
              case events loaded.
              {(data.events?.next_cursor ||
                (data.events?.total ?? 0) >
                  (data.events?.events.length ?? 0)) &&
                " Case event results are incomplete. Narrow the dates to review a complete set."}
            </p>
          )}
          {!!data.events?.events.some((e) => !validContextDate(e.date)) && (
            <p role="status">
              Some case events have unusable dates and are absent from the
              chronological display; their original records remain in the
              download.
            </p>
          )}
          <div className="flex flex-wrap gap-3">
            <label>
              Search this timeline{" "}
              <input
                aria-label="Search this timeline"
                className="border bg-background p-2"
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value)
                  setPage(0)
                }}
              />
            </label>
            <label>
              Show{" "}
              <select
                aria-label="Timeline item type"
                className="border bg-background p-2"
                value={kind}
                onChange={(e) => {
                  setKind(e.target.value)
                  setPage(0)
                }}
              >
                <option value="both">Postings and case events</option>
                <option value="posting">Ledger postings</option>
                <option value="event">Case events</option>
              </select>
            </label>
          </div>
          <p>
            {visible.length} items match this display. Case-event amounts are
            context and are never added to ledger totals.
          </p>
          {!visible.length && (
            <p>
              No items match this display. Missing or unprocessed evidence may
              change the answer.
            </p>
          )}
          <ol className="space-y-3">
            {visible.slice(page * 50, page * 50 + 50).map((item) => (
              <li key={item.key} className="border-l-2 border-primary pl-4">
                <p className="font-semibold">
                  {item.date} ·{" "}
                  {item.kind === "posting"
                    ? "Ledger posting"
                    : "Case event — context"}
                </p>
                {item.kind === "posting" ? (
                  <>
                    <p>
                      {item.row.account_label} · {item.row.direction}{" "}
                      {correctionMoney(
                        item.row.amount_minor,
                        item.row.currency
                      )}{" "}
                      · {item.row.proof_class.toUpperCase()}
                    </p>
                    <p>{chronologyLabels[item.row.chronology_basis]}</p>
                    <p>{item.row.description}</p>
                    <Button
                      variant="outline"
                      onClick={() => setSource(item.row.key)}
                    >
                      Open posting source {item.row.key.slice(0, 8)}
                    </Button>
                  </>
                ) : (
                  <>
                    <p>
                      {item.event.name} · {item.event.type}
                    </p>
                    <p className="whitespace-pre-wrap break-words">
                      {item.event.summary}
                    </p>
                    <Button
                      variant="outline"
                      onClick={() => {
                        selectNodes([item.event.key])
                        expand("detail")
                      }}
                    >
                      Open case event {item.event.name}
                    </Button>
                  </>
                )}
              </li>
            ))}
          </ol>
          {visible.length > 50 && (
            <div className="flex gap-2">
              <Button disabled={!page} onClick={() => setPage(page - 1)}>
                Previous timeline items
              </Button>
              <span>
                Page {page + 1} of {Math.ceil(visible.length / 50)}
              </span>
              <Button
                disabled={(page + 1) * 50 >= visible.length}
                onClick={() => setPage(page + 1)}
              >
                Next timeline items
              </Button>
            </div>
          )}
          <Button onClick={download}>
            Download captured timeline and display filters
          </Button>
        </>
      )}
      {source && (
        <LedgerSourceDialog
          caseId={caseId}
          transactionId={source}
          onClose={() => setSource(null)}
        />
      )}
    </div>
  )
}
