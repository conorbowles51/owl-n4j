import { useQuery } from "@tanstack/react-query"
import type { ItemInput } from "@/features/theory/api"
import { LookInto } from "@/features/relations/LookInto"
import { phoneLinkHref } from "../phone-links"
import { MAX_TOGETHER_PHONES, meetingWhen, overlapsQuery, type Meeting, type Overlaps, type Part } from "./phone-together"

function RecordLinks({ caseId, ids, total }: { caseId: string; ids: string[]; total: number }) {
  return (
    <details className="text-xs">
      <summary className="cursor-pointer underline underline-offset-2">Open the {total.toLocaleString("en-US")} {total === 1 ? "record" : "records"}</summary>
      <ul className="mt-1 flex flex-wrap gap-x-2">
        {ids.map((id, i) => {
          const href = phoneLinkHref(caseId, { target_type: "phone_record", target_id: id })
          return <li key={id}>{href ? <a className="underline" href={href}>Record {i + 1}</a> : `Record ${i + 1}`}</li>
        })}
        {total > ids.length && <li>{(total - ids.length).toLocaleString("en-US")} more are not listed here</li>}
      </ul>
    </details>
  )
}

const items = (ids: string[], label: string): ItemInput[] => ids.map((id) => ({ target_type: "phone_record" as const, target_id: id, target_label: label }))

function MeetingRow({ caseId, m, labels, onPick }: { caseId: string; m: Meeting; labels: Record<string, string>; onPick?: (m: Meeting) => void }) {
  const ids = m.phones.flatMap((p) => m.records[p] ?? [])
  const total = m.phones.reduce((n, p) => n + (m.records_total[p] ?? 0), 0)
  const names = m.phones.map((p) => labels[p] ?? p.slice(0, 8)).join(" and ")
  const label = `${names} together, ${meetingWhen(m)}`
  return (
    <li className="space-y-1 border-b py-2" data-testid="together-meeting">
      <div className="font-medium">
        <span className="text-[#6a2c91]">{names}</span> together · {meetingWhen(m)}
      </div>
      <p className="text-xs text-muted-foreground">
        {m.cells} {m.cells === 1 ? "time slot" : "time slots"} of 15 minutes in the same 550 m square
        {m.precision.accuracy_stated ? `, best accuracy ${m.precision.best_accuracy_m} m` : ", accuracy not stated"}
        {` (${m.precision.sources.join(", ")}). `}
        {m.busy?.words}
      </p>
      <div className="flex flex-wrap items-center gap-2">
        {m.busy?.is_busy && <span className="rounded border px-1.5 text-xs">Busy place: weak</span>}
        <RecordLinks caseId={caseId} ids={ids} total={total} />
        {onPick && <button type="button" className="text-xs underline" onClick={() => onPick(m)}>Show</button>}
        <LookInto caseId={caseId} surface="phone" items={items(ids, label)} />
      </div>
    </li>
  )
}

/**
 * The shared panel of the overlays: where the chosen phones were together, the people they share and the relay
 * chains. A part with nothing found says what was searched; nothing is blank.
 */
export function TogetherPanel({ caseId, phoneIds, from, to, parts, onPick, data }: {
  caseId: string; phoneIds: string[]; from?: string | null; to?: string | null; parts: Part[]; onPick?: (m: Meeting) => void
  /** Already read by the screen (it draws the same result). */
  data?: Overlaps
}) {
  const q = useQuery({ ...overlapsQuery(caseId, phoneIds, from, to, parts), enabled: !data && phoneIds.length >= 2 && phoneIds.length <= MAX_TOGETHER_PHONES })
  const out = data ?? q.data
  if (phoneIds.length < 2) return <p role="status" className="px-3 py-2 text-sm" data-testid="together-panel">Switch on at least two phones to see where they were together.</p>
  if (phoneIds.length > MAX_TOGETHER_PHONES) return <p role="status" className="px-3 py-2 text-sm" data-testid="together-panel">{phoneIds.length} phones are on. Switch off down to {MAX_TOGETHER_PHONES} or fewer to see where they were together.</p>
  if (!data && q.isLoading) return <p role="status" className="px-3 py-2 text-sm" data-testid="together-panel">Reading where these phones were together</p>
  if (!out) return <p role="alert" className="px-3 py-2 text-sm" data-testid="together-panel">Where the phones were together could not be read. Try again.</p>
  const labels = Object.fromEntries(out.phones.map((p) => [p.id, p.label]))
  return (
    <section className="max-h-48 space-y-2 overflow-auto border-b bg-card px-3 py-2 text-sm" data-testid="together-panel" aria-label="Phones together">
      {parts.includes("places") && (
        <div>
          <h3 className="font-semibold">Together in the same place: {out.together.length.toLocaleString("en-US")} {out.together.length === 1 ? "meeting" : "meetings"}</h3>
          {out.together.length === 0 && <p role="status">{out.message}</p>}
          <ul>{out.together.map((m) => <MeetingRow key={m.id} caseId={caseId} m={m} labels={labels} onPick={onPick} />)}</ul>
        </div>
      )}
      {parts.includes("contacts") && (
        <div>
          <h3 className="font-semibold">People on more than one of these phones: {out.shared_contacts.length.toLocaleString("en-US")}</h3>
          {out.shared_contacts.length === 0 && <p role="status">{out.contacts_message}</p>}
          <ul>
            {out.shared_contacts.map((c) => (
              <li key={c.id} className="space-y-1 border-b py-2" data-testid="together-contact">
                <div className="font-medium">{c.label}</div>
                <p className="text-xs text-muted-foreground">
                  {Object.entries(c.phones).map(([p, s]) => `${labels[p] ?? p.slice(0, 8)}: ${s.records.toLocaleString("en-US")}`).join(" · ")}. {c.basis}.
                </p>
                <div className="flex flex-wrap items-center gap-2">
                  <RecordLinks caseId={caseId} ids={Object.values(c.phones).flatMap((s) => s.record_ids)} total={c.records} />
                  <LookInto caseId={caseId} surface="phone" items={items(Object.values(c.phones).flatMap((s) => s.record_ids), `Shared contact ${c.label}`)} />
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
      {parts.includes("relay") && (
        <div>
          <h3 className="font-semibold">Relay chains: {out.relay_chains.length.toLocaleString("en-US")}</h3>
          {out.relay_chains.length === 0 && <p role="status">{out.relay_message}</p>}
          <ul>
            {out.relay_chains.map((r) => (
              <li key={r.id} className="space-y-1 border-b py-2 pl-2 [border-left:3px_solid_#6a2c91]" data-testid="together-relay">
                <div>
                  <span className="font-medium">{r.via_label}</span> dealt with {labels[r.first] ?? r.first.slice(0, 8)}, then {labels[r.second] ?? r.second.slice(0, 8)} {Math.max(1, Math.round(r.gap_s / 60))} {Math.round(r.gap_s / 60) <= 1 ? "minute" : "minutes"} later ({new Date(r.first_at).toISOString().slice(0, 16).replace("T", " ")} UTC)
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <RecordLinks caseId={caseId} ids={r.records} total={r.records.length} />
                  <LookInto caseId={caseId} surface="phone" items={items(r.records, `Relay via ${r.via_label}`)} />
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
      <details className="text-xs text-muted-foreground">
        <summary className="cursor-pointer">What was searched</summary>
        <ul className="list-disc pl-5">{out.searched.map((s) => <li key={s}>{s}</li>)}{out.out_of_reach.map((s) => <li key={s}>Out of reach: {s}</li>)}</ul>
      </details>
    </section>
  )
}
