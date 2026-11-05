import { useState } from "react"
import { Link, useParams } from "react-router-dom"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { fetchAPI } from "@/lib/api-client"
import { citationHref } from "@/features/financial/lib/judgements"
import { caseMembersAPI } from "@/features/cases/members-api"

/**
 * Monitoring apps beside bank control notices (coercive control, economic abuse). An indicator with its basis, never a
 * finding: a listed app says what the app is listed as, not who installed or used it. The list is sourced and a person
 * edits it for the case: add with a source, review, or set aside with the reason.
 */
interface LaneItem {
  kind: "monitoring_app" | "bank_control"
  rec: string
  phone?: string | null
  at?: string | null
  label: string
  identifier?: string
  listed_as?: string
  basis?: string
  reviewed?: boolean
  name_on_phone?: string | null
  deleted_state?: string | null
  notice?: string
  sender?: string | null
  institution?: string | null
}

interface ListEdit { id: string; identifier: string; label: string | null; action: "add" | "reviewed" | "set_aside"; source: string | null; reason: string; by: string }

interface Indicators {
  label: string
  limits: string
  total: number
  monitoring_apps: number
  bank_control_notices: number
  items: LaneItem[]
  set_aside: LaneItem[]
  outside_dates: number
  coverage: string
  not_read: string
  list_summary: { version: string | null; apps: number; identifiers: number; source: { name: string; url: string; license: string; commit: string; retrieved_on: string; note: string } | null; edits: ListEdit[] }
}

const base = (caseId: string) => `/api/phone-monitoring/${encodeURIComponent(caseId)}`
const ACTION_WORDS = { add: "Added", reviewed: "Reviewed", set_aside: "Set aside" }

function Item({ caseId, item }: { caseId: string; item: LaneItem }) {
  const href = citationHref(caseId, item.rec)
  const when = item.at ? item.at.slice(0, 16).replace("T", " ") : "No time recorded"
  return (
    <li className="rounded border p-2 text-sm" data-testid="monitoring-item" data-kind={item.kind}>
      <p className="font-medium">
        {href ? <a className="underline" href={href} target="_blank" rel="noreferrer">{when}</a> : when}
        {item.phone ? ` · ${item.phone}` : ""}
      </p>
      {item.kind === "monitoring_app" ? (
        <>
          <p>{item.name_on_phone || item.identifier} ({item.identifier}), listed as {item.listed_as}.{item.deleted_state === "deleted" ? " The record is deleted." : ""}</p>
          <p className="text-xs" data-testid="monitoring-basis">{item.basis}</p>
        </>
      ) : (
        <p>Notice of {item.notice}{item.institution ? ` from ${item.institution}` : item.sender ? ` from ${item.sender}` : ""}.</p>
      )}
      <p className="text-xs text-muted-foreground">{item.label}</p>
    </li>
  )
}

export default function MonitoringAppsPage() {
  const { id: caseId = "" } = useParams()
  const client = useQueryClient()
  // case edit permission as the server grants it; when the membership cannot be read the server decides
  const membership = useQuery({ queryKey: ["case-membership-mapped", caseId], queryFn: () => caseMembersAPI.getMyMembership(caseId), enabled: !!caseId, retry: false })
  const canEdit = membership.isError ? true : !!(membership.data?.permissions as { case?: { edit?: boolean } } | undefined)?.case?.edit
  const [start, setStart] = useState("")
  const [end, setEnd] = useState("")
  const [identifier, setIdentifier] = useState("")
  const [source, setSource] = useState("")
  const [reason, setReason] = useState("")
  const [action, setAction] = useState<ListEdit["action"]>("add")
  const [err, setErr] = useState<string | null>(null)
  const q = useQuery({
    queryKey: ["monitoring-apps", caseId, start, end],
    queryFn: () => fetchAPI<Indicators>(`${base(caseId)}?${new URLSearchParams({ ...(start ? { start } : {}), ...(end ? { end } : {}) })}`),
  })
  const refresh = () => client.invalidateQueries({ queryKey: ["monitoring-apps", caseId] })
  const save = () =>
    fetchAPI(`${base(caseId)}/entries`, { method: "POST", body: { identifier, action, reason, ...(source ? { source } : {}) } })
      .then(() => { setIdentifier(""); setReason(""); setSource(""); setErr(null); return refresh() })
      .catch((e: Error) => setErr(e.message))
  const remove = (id: string) => fetchAPI(`${base(caseId)}/entries/${id}`, { method: "DELETE" }).then(refresh).catch((e: Error) => setErr(e.message))
  const d = q.data
  const src = d?.list_summary.source
  return (
    <div className="space-y-3 p-4" data-testid="monitoring-apps-page">
      <p className="text-sm"><Link className="underline" to={`/cases/${caseId}/phone-analyses`}>Phone analyses</Link></p>
      <h1 className="text-lg font-semibold">Monitoring apps and bank notices</h1>
      <p className="text-sm">Installed apps on a sourced list, beside notices of bank changes on the phones, in date order.</p>
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <label className="flex items-center gap-2">From <Input type="date" className="h-8 w-40" value={start} onChange={(e) => setStart(e.target.value)} /></label>
        <label className="flex items-center gap-2">To <Input type="date" className="h-8 w-40" value={end} onChange={(e) => setEnd(e.target.value)} /></label>
      </div>
      {q.isPending ? <p role="status">Comparing the phones' apps and notices with the list…</p> : q.isError ? <p role="alert">{q.error.message}</p> : d && (
        <>
          <p className="text-sm font-medium" data-testid="monitoring-counts">
            {d.label}: {d.monitoring_apps.toLocaleString("en-US")} listed {d.monitoring_apps === 1 ? "app" : "apps"}, {d.bank_control_notices.toLocaleString("en-US")} bank {d.bank_control_notices === 1 ? "notice" : "notices"}.
            {d.outside_dates > 0 ? ` ${d.outside_dates.toLocaleString("en-US")} more fall outside these dates.` : ""}
          </p>
          <p className="text-xs" data-testid="monitoring-limits">{d.limits}</p>
          <p className="text-xs text-muted-foreground">{d.coverage} {d.not_read}</p>
          {d.items.length === 0 ? <p className="text-sm">Nothing on the list or among the notices.</p> : (
            <ul className="space-y-2">{d.items.map((x) => <Item key={x.rec} caseId={caseId} item={x} />)}</ul>
          )}
          {d.set_aside.length > 0 && (
            <section aria-label="Set aside" className="space-y-2">
              <h2 className="text-sm font-medium">Set aside by a person</h2>
              <ul className="space-y-2">{d.set_aside.map((x) => <Item key={x.rec} caseId={caseId} item={x} />)}</ul>
            </section>
          )}
          <section aria-label="The list" className="space-y-2 text-sm">
            <h2 className="font-medium">The list</h2>
            {src && <p className="text-xs" data-testid="monitoring-source">{d.list_summary.apps.toLocaleString("en-US")} apps, {d.list_summary.identifiers.toLocaleString("en-US")} identifiers, from <a className="underline" href={src.url} target="_blank" rel="noreferrer">{src.name}</a> ({src.license}), retrieved {src.retrieved_on}. {src.note}</p>}
            {d.list_summary.edits.length > 0 && (
              <ul className="space-y-1 text-xs">
                {d.list_summary.edits.map((e) => (
                  <li key={e.id} className="flex flex-wrap items-center gap-2" data-testid="monitoring-edit">
                    {ACTION_WORDS[e.action]}: {e.label || e.identifier} by {e.by}. {e.reason}{e.source ? ` Source: ${e.source}.` : ""}
                    {canEdit && <Button size="sm" variant="outline" onClick={() => remove(e.id)}>Remove this edit</Button>}
                  </li>
                ))}
              </ul>
            )}
            {canEdit && (
              <div className="flex flex-wrap items-end gap-2">
                <label className="flex flex-col text-xs">Edit
                  <select aria-label="Edit" className="h-8 rounded border bg-background px-2" value={action} onChange={(e) => setAction(e.target.value as ListEdit["action"])}>
                    <option value="add">Add an identifier</option>
                    <option value="reviewed">Mark a list entry reviewed</option>
                    <option value="set_aside">Set a list entry aside</option>
                  </select>
                </label>
                <Input aria-label="App identifier" className="h-8 w-64" placeholder="App identifier" value={identifier} onChange={(e) => setIdentifier(e.target.value)} />
                {action === "add" && <Input aria-label="Source" className="h-8 w-64" placeholder="Source (required)" value={source} onChange={(e) => setSource(e.target.value)} />}
                <Input aria-label="Why" className="h-8 w-64" placeholder="Why" value={reason} onChange={(e) => setReason(e.target.value)} />
                <Button size="sm" disabled={!identifier.trim() || !reason.trim() || (action === "add" && !source.trim())} onClick={save}>Save</Button>
              </div>
            )}
            {err && <p role="alert" className="text-xs text-destructive">{err}</p>}
          </section>
        </>
      )}
    </div>
  )
}
