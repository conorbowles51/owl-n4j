import { useQueries, useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { Link } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { CopyButton } from "@/components/ui/copy-button"
import { ApiError, fetchAPI } from "@/lib/api-client"
import { recordPath } from "@/lib/record-links"
import { CorroborateAction } from "@/features/leads/CorroborateAction"
import { failureText, getRecord } from "../api"
import { liveCollectClient } from "../collect.api"
import { useCollectTargets } from "../collect-targets"
import { RecordDetailView } from "../components/RecordPanel"
import { labelText } from "../lib/labels"
import type { StreamRow } from "../schemas"
import { AddToMenu } from "../ui/AddToMenu"
import { citationHref, copyWithSource, rowText, rowTitle } from "./home-words"
import { PhoneShape } from "../ui/PhoneChip"

/**
 * The Phones page's record panel (screen 1): it follows the focused row of the list (j/k move it). Details and
 * source, "Elsewhere in the case" (lx-elsewhere's rule-computed relations, one request per part, each shown as it
 * arrives) and the actions: Add to the case, Read the thread, That day on all phones, Corroborate, Copy with source.
 */

export const ELSEWHERE_PARTS = ["phones", "financial", "documents", "timeline"] as const
export type ElsewherePart = (typeof ELSEWHERE_PARTS)[number]
const PART_WORDS: Record<ElsewherePart, string> = { phones: "Phones", financial: "Financial", documents: "Documents", timeline: "Timeline" }

export interface ElsewhereItem {
  relation: string
  relation_label: string
  text: string
  reason?: string | null
  citation?: { kind: string; id: string; label?: string | null; phone?: string | null; page?: number | null } | null
}
export interface ElsewhereAnswer {
  parts: { source: string; label: string; state: "done" | "failed"; searched?: string; items: ElsewhereItem[] }[]
}

/** Sent when the elsewhere service is not on this server yet: the panel then checks the other phones only. */
export const ELSEWHERE_MISSING = "missing"

async function elsewhere(caseId: string, recordUid: string, part: ElsewherePart): Promise<ElsewhereAnswer | typeof ELSEWHERE_MISSING> {
  try {
    return await fetchAPI<ElsewhereAnswer>(`/api/cases/${encodeURIComponent(caseId)}/elsewhere/record/${encodeURIComponent(recordUid)}?part=${part}`, { read: true })
  } catch (e) {
    // the route itself is not on this server (FastAPI's own "Not Found"), not a record the service could not find
    if (e instanceof ApiError && (e.status === 404 || e.status === 405) && /^(Not Found|Method Not Allowed)$/.test(e.message ?? "")) return ELSEWHERE_MISSING
    throw e
  }
}

const PILL: Record<ElsewherePart, string> = {
  phones: "bg-sky-100 text-sky-900 dark:bg-sky-400/15 dark:text-sky-100",
  financial: "bg-emerald-100 text-emerald-900 dark:bg-emerald-400/15 dark:text-emerald-100",
  documents: "bg-indigo-100 text-indigo-900 dark:bg-indigo-400/15 dark:text-indigo-100",
  timeline: "bg-amber-100 text-amber-900 dark:bg-amber-400/15 dark:text-amber-100",
}

/** Other phones in scope holding the same message or call (same kind, minute and text): the fallback check. */
function OtherPhonesOnly({ row, alsoOn }: { row: StreamRow; alsoOn: string[] }) {
  return (
    <div className="flex gap-2 border-t pt-2 text-xs">
      <span className={`w-20 shrink-0 rounded-full px-2 py-0.5 text-center font-semibold ${PILL.phones}`}>Phones</span>
      <span className="leading-snug">
        {alsoOn.length ? `Also on ${alsoOn.join(" and ")}.` : `Not found on any other phone that is on.`}{" "}
        <span className="text-muted-foreground">Only the other phones were checked; financial records, documents and the timeline are not checked from here yet.</span>
        {row.kind === "record" && <span className="text-muted-foreground"> Records other than messages and calls are not compared across phones.</span>}
      </span>
    </div>
  )
}

function Elsewhere({ caseId, row, alsoOn }: { caseId: string; row: StreamRow; alsoOn: string[] }) {
  const parts = useQueries({
    queries: ELSEWHERE_PARTS.map((part) => ({
      queryKey: ["elsewhere-record", caseId, row.record_uid, part],
      queryFn: () => elsewhere(caseId, row.record_uid, part),
      retry: false,
      staleTime: 60_000,
    })),
  })
  const missing = parts.some((p) => p.data === ELSEWHERE_MISSING)
  return (
    <section aria-label="Elsewhere in the case" className="flex flex-col gap-2 rounded-lg border bg-card p-3">
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold">Elsewhere in the case</h3>
        <span className="text-xs text-muted-foreground">checked when you opened it</span>
      </div>
      {missing ? (
        <OtherPhonesOnly row={row} alsoOn={alsoOn} />
      ) : (
        ELSEWHERE_PARTS.map((part, i) => {
          const q = parts[i]
          const pill = <span className={`w-20 shrink-0 rounded-full px-2 py-0.5 text-center text-xs font-semibold ${PILL[part]}`}>{PART_WORDS[part]}</span>
          if (q.isPending) return <div key={part} className="flex gap-2 border-t pt-2 text-xs">{pill}<span className="text-muted-foreground" role="status">Checking</span></div>
          if (q.isError) return <div key={part} className="flex gap-2 border-t pt-2 text-xs">{pill}<span role="alert">{failureText(q.error, "This part of the case could not be checked.")} Open the record again to retry.</span></div>
          const a = q.data as ElsewhereAnswer
          const items = a.parts.flatMap((p) => (p.state === "failed" ? [{ relation: "failed", relation_label: "Not checked", text: `${p.label} could not be checked. Open the record again to retry.` } as ElsewhereItem] : p.items))
          return items.map((it, k) => {
            const href = it.citation ? citationHref(caseId, it.citation) : null
            return (
              <div key={`${part}-${k}`} className="flex gap-2 border-t pt-2 text-xs" data-relation={it.relation}>
                {pill}
                <span className="leading-snug">
                  <span className="font-medium">{it.relation_label}.</span> {it.text}
                  {it.reason && <span className="text-muted-foreground"> {it.reason}</span>}
                  {href && it.citation && <> <Link className="underline underline-offset-2" to={href}>{it.citation.label || "Open it"}</Link></>}
                </span>
              </div>
            )
          })
        })
      )}
    </section>
  )
}

export function HomeRecordPanel({ caseId, row, phoneIndex, alsoOn, onThatDay, onClose }: {
  caseId: string
  row: StreamRow | null
  phoneIndex: (extractionId: string) => number
  /** Labels of the other phones in scope holding the same message or call. */
  alsoOn: string[]
  onThatDay: (row: StreamRow) => void
  onClose?: () => void
}) {
  const t = useCollectTargets(caseId)
  const [full, setFull] = useState(false)
  const detail = useQuery({ queryKey: ["phone-record", caseId, row?.record_uid, undefined], queryFn: () => getRecord(caseId, row!.record_uid), enabled: !!row && full })
  if (!row)
    return (
      <aside aria-label="Selected record" className="flex flex-col gap-2 p-4 text-sm text-muted-foreground">
        <p>Choose a row to see it here with what the rest of the case holds about it. j and k move through the list.</p>
      </aside>
    )
  const comm = row.kind !== "record"
  const label = rowText(row)
  const conv = `/cases/${encodeURIComponent(caseId)}/phones/${encodeURIComponent(row.phone.extraction_id)}/records/conversations?record=${encodeURIComponent(row.record_uid)}`
  const link = `${window.location.origin}${recordPath(caseId, row.record_uid)}`
  return (
    <aside aria-label="Selected record" className="flex flex-col gap-4 p-4" data-record={row.record_uid}>
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{rowTitle(row)}</h2>
        {onClose && <Button size="sm" variant="ghost" onClick={onClose}>Close</Button>}
      </div>
      <p className="whitespace-pre-wrap text-base leading-relaxed text-foreground">{comm ? `“${label}”` : label}</p>
      <dl className="grid grid-cols-[5.5rem_1fr] gap-x-3 gap-y-2 text-sm">
        {row.from && <><dt className="text-muted-foreground">From</dt><dd className="min-w-0 break-words">{labelText(row.from)}</dd></>}
        {row.to.length > 0 && <><dt className="text-muted-foreground">To</dt><dd className="min-w-0 break-words">{row.to.map(labelText).join("; ")}</dd></>}
        <dt className="text-muted-foreground">When</dt><dd>{row.time.full}</dd>
        {row.app && <><dt className="text-muted-foreground">App</dt><dd>{row.app}</dd></>}
        <dt className="text-muted-foreground">Phone</dt><dd className="inline-flex items-center gap-1.5"><PhoneShape index={phoneIndex(row.phone.extraction_id)} />{row.phone.label}</dd>
        <dt className="text-muted-foreground">Source</dt>
        <dd><button type="button" className="text-left underline underline-offset-2" aria-expanded={full} onClick={() => setFull((v) => !v)}>{row.phone.label} report, the {comm ? (row.kind === "call" ? "call" : "message") : "record"} record</button></dd>
        {row.flags.includes("deleted") && <><dt className="text-muted-foreground">State</dt><dd>Deleted on the phone; the report still holds it</dd></>}
      </dl>
      {full && (
        <section aria-label="Every field of the record" className="rounded-lg border p-3 text-sm">
          {detail.isPending && <p role="status" className="text-muted-foreground">Loading the record</p>}
          {detail.isError && <p role="alert">{failureText(detail.error, "The record could not be loaded.")} Choose the source again to retry.</p>}
          {detail.data && <RecordDetailView detail={detail.data} caseId={caseId} />}
        </section>
      )}
      <Elsewhere caseId={caseId} row={row} alsoOn={alsoOn} />
      <div className="flex flex-col gap-2" aria-label="What to do with it">
        <AddToMenu caseId={caseId} links={[{ target_type: "phone_record", target_id: row.record_uid, label, source_anchor: { origin: "phones_page" } }]}
          noun="record" targets={t.targets} client={liveCollectClient} origin="Added from the Phones page" keys={false}
          label="Add to the case" corroborate={false} buttonClassName="h-10 w-full" />
        <div className="grid grid-cols-2 gap-2">
          {comm ? (
            <Button asChild variant="outline" size="sm"><Link to={conv}>Read the thread</Link></Button>
          ) : (
            <Button asChild variant="outline" size="sm"><Link to={recordPath(caseId, row.record_uid)}>Open the record</Link></Button>
          )}
          <Button variant="outline" size="sm" disabled={!row.time.instant} disabledReason="This record has no time, so it has no day." onClick={() => onThatDay(row)}>That day, all phones</Button>
          <CorroborateAction caseId={caseId} screen="Phones" label={label.length > 60 ? `${label.slice(0, 57)}...` : label}
            members={[{ type: "phone_record", id: row.record_uid, label }]} />
          <CopyButton rows={1} noun="record" label="Copy with source"
            build={() => ({ text: copyWithSource(row, link) })} />
        </div>
      </div>
    </aside>
  )
}
