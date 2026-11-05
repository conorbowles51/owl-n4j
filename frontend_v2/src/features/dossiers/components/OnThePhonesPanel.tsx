import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { Link } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { countHref, dayOf, peopleAPI, type DossierPhones, type PanelDecision, type PanelPhone } from "@/features/phones/people.api"
import { errorWords, identitiesAPI } from "@/features/phones/review/identities.api"

const fmt = (n: number) => n.toLocaleString("en-US")
const KIND_WORDS: Record<string, [string, string]> = {
  message: ["message", "messages"],
  call: ["call", "calls"],
  email: ["email", "emails"],
  chat_activity: ["chat event", "chat events"],
}
const DIRECTION_WORDS: Record<string, string> = { incoming: "in", outgoing: "out", unknown: "direction not recorded" }
const DECISION_WORDS: Record<string, string> = {
  link_phone_identity: "Linked",
  unlink_phone_identity: "Unlinked",
  reject_phone_identity_link: "Marked not the same person",
  restore_phone_identity_link: "Restored as a possible match",
}
const NOT_ALLOWED = "A case admin can change links."

/**
 * On the phones (03 section 10.2; 07 J-3, J-16, XF-5): the identities linked to this person, then per phone the names
 * that phone holds, the contact's dates, counts by channel and direction, first and last contact. Every count opens
 * the records it counts. Suggestions are stated apart, and links are changed only through a decision with a named
 * actor, reversible from the history here.
 */
export function OnThePhonesPanel({ caseId, dossierId, canEdit }: { caseId: string; dossierId: string; canEdit: boolean }) {
  const q = useQuery({
    queryKey: ["dossier-phones", caseId, dossierId],
    queryFn: () => peopleAPI.dossierPhones(caseId, dossierId),
    staleTime: 30_000,
  })
  return (
    <section aria-label="On the phones" className="space-y-3 rounded-xl border border-border p-4 text-sm">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">On the phones</h3>
      {q.isLoading && <p role="status">Reading the phones</p>}
      {q.isError && (
        <div role="alert">
          <p>The phones could not be read. {errorWords(q.error)}</p>
          <Button size="sm" variant="outline" className="mt-1" onClick={() => void q.refetch()}>Try again</Button>
        </div>
      )}
      {q.data && <Panel data={q.data} caseId={caseId} canEdit={canEdit} />}
    </section>
  )
}

function Panel({ data, caseId, canEdit }: { data: DossierPhones; caseId: string; canEdit: boolean }) {
  const name = data.dossier.name
  const base = `/cases/${encodeURIComponent(caseId)}`
  const phoneIds = data.phones.map((p) => p.extraction_id)
  const busiest = [...data.identities].sort((a, b) => b.events - a.events)[0]?.identity_key ?? ""
  return (
    <>
      {data.suggested_identities > 0 && (
        <p>
          Suggested, not reviewed: {fmt(data.suggested_identities)} more {data.suggested_identities === 1 ? "identity" : "identities"} may be {name}. None is counted here.{" "}
          <Link className="underline underline-offset-2" to={`${data.review_href}?panel=people`}>Review the suggestions</Link>
        </p>
      )}
      {data.identities.length === 0 ? (
        <p>
          No phone number, address or account on the phones is linked to {name} yet.{" "}
          <Link className="underline underline-offset-2" to={`${base}/dossiers?tab=phone-identities`}>Link one in Phone identities</Link>
        </p>
      ) : (
        <>
          <p>
            {data.conversations_href && (
              <Link className="font-medium underline underline-offset-2" to={data.conversations_href}>
                {fmt(data.total)} {data.total === 1 ? "message or call" : "messages and calls"} with {name}
              </Link>
            )}{" "}
            on {fmt(data.phones.filter((p) => p.total > 0).length)} of {fmt(data.phones_in_case)} {data.phones_in_case === 1 ? "phone" : "phones"}.
          </p>
          <div className="flex flex-wrap gap-2">
            {phoneIds.length > 0 && (
              <Button asChild size="sm" variant="outline">
                <Link to={`${base}/conversations?phones=${phoneIds.map(encodeURIComponent).join(",")}`}>Scope to {phoneIds.length === 1 ? "this phone" : `these ${fmt(phoneIds.length)} phones`}</Link>
              </Button>
            )}
            {phoneIds.length >= 2 && (
              <Button asChild size="sm" variant="outline">
                <Link to={`${base}/phones?compare=${phoneIds.slice(0, 2).map(encodeURIComponent).join(",")}&person=${encodeURIComponent(busiest)}`}>Compare phones</Link>
              </Button>
            )}
          </div>
          <Identities data={data} caseId={caseId} canEdit={canEdit} />
          {data.phones.map((p) => <Phone key={p.extraction_id} p={p} />)}
        </>
      )}
      <History data={data} caseId={caseId} canEdit={canEdit} />
    </>
  )
}

function Phone({ p }: { p: PanelPhone }) {
  return (
    <article aria-label={`On ${p.label}`} className="space-y-1 rounded border p-2 text-xs">
      <div className="flex flex-wrap items-baseline gap-2">
        <h4 className="text-sm font-medium">{p.label}</h4>
        <span>{p.total ? `${dayOf(p.first_contact)} to ${dayOf(p.last_contact)}` : "No messages or calls"}</span>
        <Link className="ml-auto underline underline-offset-2" to={p.conversations_href}>Open conversations ({fmt(p.total)})</Link>
      </div>
      {p.names.length > 0 ? (
        <ul>
          {p.names.map((n, i) => (
            <li key={i}>
              {n.name}
              {n.value_display ? ` (${n.value_display})` : ""}
              {n.contact_created || n.contact_modified
                ? ` · contact created ${dayOf(n.contact_created)}, changed ${dayOf(n.contact_modified)}`
                : ""}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-muted-foreground">This phone holds no name for them.</p>
      )}
      <ul className="flex flex-wrap gap-x-3">
        {p.kinds.flatMap((k) =>
          k.directions.map((d) => (
            <li key={`${k.kind}-${d.direction}`}>
              <Link className="underline underline-offset-2" to={countHref(p.conversations_href, k.kind, d.direction)}>
                {fmt(d.events)} {(KIND_WORDS[k.kind] ?? [k.kind, k.kind])[d.events === 1 ? 0 : 1]} {DIRECTION_WORDS[d.direction] ?? d.direction}
              </Link>
            </li>
          )),
        )}
      </ul>
    </article>
  )
}

function useDecide(caseId: string, dossierId: string) {
  const client = useQueryClient()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const run = async (body: Parameters<typeof identitiesAPI.decide>[1]) => {
    setBusy(true)
    setError(null)
    try {
      await identitiesAPI.decide(caseId, body)
      return true
    } catch (e) {
      setError(errorWords(e))
      return false
    } finally {
      await client.invalidateQueries({ queryKey: ["dossier-phones", caseId, dossierId] })
      await client.invalidateQueries({ queryKey: ["phone-identities", caseId] })
      await client.invalidateQueries({ queryKey: ["phone-scope-presets", caseId] })
      setBusy(false)
    }
  }
  return { busy, error, run }
}

/** The linked identities. Unlink one, or Split several out in one transaction: both preview and need a typed reason. */
function Identities({ data, caseId, canEdit }: { data: DossierPhones; caseId: string; canEdit: boolean }) {
  const [picked, setPicked] = useState<string[]>([])
  const [reason, setReason] = useState("")
  const [confirming, setConfirming] = useState(false)
  const { busy, error, run } = useDecide(caseId, data.dossier.id)
  const chosen = data.identities.filter((i) => picked.includes(i.identity_key))
  const leaving = chosen.reduce((n, i) => n + i.events, 0)
  return (
    <div className="space-y-1">
      <ul aria-label="Linked identities" className="space-y-0.5 text-xs">
        {data.identities.map((i) => (
          <li key={i.identity_key} className="flex flex-wrap items-center gap-2">
            <label className="inline-flex items-center gap-1.5">
              <input
                type="checkbox"
                disabled={!canEdit}
                title={canEdit ? undefined : NOT_ALLOWED}
                checked={picked.includes(i.identity_key)}
                onChange={(e) => setPicked((p) => (e.target.checked ? [...p, i.identity_key] : p.filter((k) => k !== i.identity_key)))}
              />
              <span className="sr-only">Choose {i.value_display}</span>
              <span className="break-all">{i.value_display ?? i.identity_key}</span>
            </label>
            <Link className="underline underline-offset-2" to={i.conversations_href}>
              {fmt(i.events)} {i.events === 1 ? "message or call" : "messages and calls"} on {fmt(i.phones)} {i.phones === 1 ? "phone" : "phones"}
            </Link>
          </li>
        ))}
      </ul>
      {!canEdit && <p className="text-xs text-muted-foreground">{NOT_ALLOWED}</p>}
      {canEdit && chosen.length > 0 && (
        <Button size="sm" variant="outline" onClick={() => setConfirming(true)}>
          {chosen.length === 1 ? "Unlink" : `Split ${fmt(chosen.length)} out of ${data.dossier.name}`}
        </Button>
      )}
      {confirming && chosen.length > 0 && (
        <div className="space-y-1 rounded border p-2 text-xs" role="group" aria-label="Unlink preview">
          <p>
            {chosen.map((i) => i.value_display ?? i.identity_key).join(", ")} will no longer count as {data.dossier.name}: their {fmt(leaving)}{" "}
            {leaving === 1 ? "message or call leaves" : "messages and calls leave"} this panel. The records stay on the phones and in Conversations. You can link them again from the history here.
          </p>
          <label className="flex flex-col gap-1">
            Your reason (required)
            <textarea className="rounded border bg-background px-2 py-1" rows={2} maxLength={4000} value={reason} onChange={(e) => setReason(e.target.value)} />
          </label>
          <div className="flex gap-2">
            <Button
              size="sm"
              disabled={busy || !reason.trim()}
              onClick={async () => {
                const ok = await run({
                  decision: chosen.length === 1 ? "unlink_phone_identity" : "split",
                  identity_keys: chosen.map((i) => i.identity_key),
                  reason: reason.trim(),
                })
                if (ok) {
                  setPicked([])
                  setReason("")
                  setConfirming(false)
                }
              }}
            >
              Confirm
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setConfirming(false)}>Cancel</Button>
          </div>
        </div>
      )}
      {error && <p role="alert" className="text-xs">{error}</p>}
    </div>
  )
}

function History({ data, caseId, canEdit }: { data: DossierPhones; caseId: string; canEdit: boolean }) {
  const { busy, error, run } = useDecide(caseId, data.dossier.id)
  if (data.history_total === 0) return null
  const linkedNow = new Set(data.identities.map((i) => i.identity_key))
  const undo = (h: PanelDecision) => {
    if (h.decision === "unlink_phone_identity" && !linkedNow.has(h.identity_key)) {
      return { words: "Link again", body: { decision: "link_phone_identity" as const, identity_keys: [h.identity_key], dossier_id: data.dossier.id, reason: "Linked again from this dossier's history" } }
    }
    if (h.decision === "reject_phone_identity_link") {
      return { words: "Restore", body: { decision: "restore_phone_identity_link" as const, identity_keys: [h.identity_key], dossier_id: data.dossier.id } }
    }
    return null
  }
  return (
    <details>
      <summary className="cursor-pointer text-xs font-medium">Link decisions ({fmt(data.history_total)})</summary>
      {data.history_total > data.history.length && (
        <p className="text-xs">Showing the newest {fmt(data.history.length)} of {fmt(data.history_total)}.</p>
      )}
      <ul className="mt-1 space-y-1 text-xs">
        {data.history.map((h) => {
          const action = undo(h)
          return (
            <li key={h.id}>
              {DECISION_WORDS[h.decision] ?? h.decision}: {h.value_display ?? h.identity_key} by {h.actor ?? "a person"}, {dayOf(h.at)}. {h.reason}{" "}
              {action && canEdit && (
                <button type="button" className="underline underline-offset-2" disabled={busy} onClick={() => void run(action.body)}>
                  {action.words}
                </button>
              )}
            </li>
          )
        })}
      </ul>
      {error && <p role="alert" className="text-xs">{error}</p>}
    </details>
  )
}
