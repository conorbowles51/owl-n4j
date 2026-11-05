import { useState } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { dossiersAPI } from "@/features/dossiers/api"
import { fmt } from "../ui/count-sentence"
import { errorWords, identitiesAPI, type IdentitySuggestion } from "./identities.api"

/**
 * Needs a decision, link to a person (02 sections 8.7 and 8.8; 07 J-7). Opened from the graph's "Add to Dossiers"
 * on a phone identity (/cases/:id/phone-review?decision=link_phone_identity&identity=<key>). The person sees the
 * identity's value and each phone's names for it, and any suggestion with its reasons; a link records the standard
 * reason built from the reasons shown, an unlink needs the person's own reason. A change made by someone else
 * meanwhile is refused and shown.
 */
const REASON_WORDS: Record<string, string> = {
  same_card: "listed together on one contact card",
  owner_accounts: "the phone's own account",
  dossier_contact: "a contact detail on this person's dossier",
  name_support: "the same name",
  financial_identifier: "an account identifier on a statement",
}

/** The words the ledger stores (services/phone/identity_decisions.standard_link_reason): reason kinds sorted. */
function standardReason(s: IdentitySuggestion | undefined) {
  const kinds = [...new Set((s?.reasons ?? []).map((r) => r.reason))].sort().map((k) => REASON_WORDS[k] ?? k)
  return kinds.length ? `Linked on the review screen after seeing: ${kinds.join("; ")}` : "Linked on the review screen"
}

function SuggestionLine({ s }: { s: IdentitySuggestion }) {
  return (
    <span>
      {s.reasons.map((r) => REASON_WORDS[r.reason] ?? r.reason).join("; ")}
      {s.reasons.some((r) => r.phones.length) ? ` (on ${[...new Set(s.reasons.flatMap((r) => r.phones))].join(", ")})` : ""}
    </span>
  )
}

export function IdentityLinkGroup({ caseId, identityKey }: { caseId: string; identityKey: string }) {
  const client = useQueryClient()
  const detail = useQuery({ queryKey: ["phone-identity", caseId, identityKey], queryFn: () => identitiesAPI.get(caseId, identityKey) })
  const sugg = useQuery({ queryKey: ["phone-identity-suggestions", caseId], queryFn: () => identitiesAPI.suggestions(caseId) })
  const people = useQuery({ queryKey: ["dossiers", caseId, "phone-link"], queryFn: () => dossiersAPI.list({ caseId, limit: 200 }) })
  const [target, setTarget] = useState<string>("")
  const [newName, setNewName] = useState("")
  const [reason, setReason] = useState("")
  const [note, setNote] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (detail.isLoading) return <p role="status" className="text-sm">Loading this identity.</p>
  if (detail.isError) return <p role="alert" className="text-sm">This identity could not be loaded. {errorWords(detail.error)}</p>
  const d = detail.data!
  const mine = (sugg.data?.suggestions ?? []).filter((s) => s.identities.some((i) => i.identity_key === d.identity_key))
  const toDossier = mine.find((s) => s.dossier_id && s.dossier_id === target)
  const shown = toDossier ?? (target === "new" ? mine.find((s) => !s.dossier_id) : undefined)
  const nameOf = (id: string | null) => people.data?.dossiers.find((p) => p.id === id)?.display_name ?? "a person"

  const refresh = async () => {
    await client.invalidateQueries({ queryKey: ["phone-identity", caseId, identityKey] })
    await client.invalidateQueries({ queryKey: ["phone-identity-suggestions", caseId] })
  }
  const run = async (body: Parameters<typeof identitiesAPI.decide>[1], words: string) => {
    if (busy) return
    setBusy(true)
    setError(null)
    setDone(null)
    try {
      await identitiesAPI.decide(caseId, body)
      setDone(words)
      setReason("")
      setNote("")
      await client.invalidateQueries({ queryKey: ["dossiers", caseId] })
    } catch (e) {
      setError(errorWords(e))
    } finally {
      await refresh()
      setBusy(false)
    }
  }
  const link = () => {
    if (!target || (target === "new" && !newName.trim())) return
    void run(
      {
        decision: "link_phone_identity",
        identity_keys: [d.identity_key],
        ...(target === "new" ? { new_person_name: newName.trim() } : { dossier_id: target }),
        reasons_shown: shown ? shown.reasons.map((r) => ({ reason: r.reason })) : undefined,
        note: note.trim() || undefined,
        expected_revision: d.expected_revision,
      },
      target === "new" ? `Linked to a new person, ${newName.trim()}.` : `Linked to ${nameOf(target)}.`
    )
  }
  const unlink = () => {
    if (!reason.trim()) return
    void run(
      { decision: "unlink_phone_identity", identity_keys: [d.identity_key], reason: reason.trim(), note: note.trim() || undefined, expected_revision: d.expected_revision },
      "Unlinked."
    )
  }
  const reject = (s: IdentitySuggestion) => {
    const other = s.identities.find((i) => i.identity_key !== d.identity_key)
    void run(
      {
        decision: "reject_phone_identity_link",
        identity_keys: [d.identity_key],
        ...(s.dossier_id ? { dossier_id: s.dossier_id } : other ? { target_identity_key: other.identity_key } : {}),
      },
      "Marked as not the same person. It will not be suggested again."
    )
  }

  return (
    <section aria-labelledby="identity-link" className="flex flex-col gap-3 rounded border bg-card p-3">
      <h2 id="identity-link" className="text-base font-semibold">Link to a person</h2>
      <p className="text-base">{d.value_display}</p>
      <p className="text-sm text-muted-foreground">
        Seen {fmt(d.sightings)} {d.sightings === 1 ? "time" : "times"} on {fmt(d.phones)} {d.phones === 1 ? "phone" : "phones"} in this case.
      </p>
      {d.names.length > 0 ? (
        <ul aria-label="Names on each phone" className="flex flex-col gap-0.5 text-sm">
          {d.names.map((n, i) => (
            <li key={i}>
              {n.phone}: {n.name}
              {n.is_phone_name ? " (the name this phone uses)" : ""} · {fmt(n.occurrences)} {n.occurrences === 1 ? "time" : "times"}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm">No phone gives a name for it.</p>
      )}
      {!d.can_be_a_person ? (
        <p className="text-sm">This is a group, not a person, so it cannot be linked to one.</p>
      ) : d.linked_dossier ? (
        <div className="flex flex-col gap-2 text-sm">
          <p role="status">Linked to {d.linked_dossier.name ?? "a person"}.</p>
          <label className="flex flex-col gap-1">
            Your reason for unlinking (required)
            <textarea className="rounded border bg-background px-2 py-1" rows={2} maxLength={4000} value={reason} onChange={(e) => setReason(e.target.value)} />
          </label>
          <div>
            <Button size="sm" variant="outline" onClick={unlink} disabled={!reason.trim() || busy}>Unlink</Button>
          </div>
        </div>
      ) : (
        <div className="flex flex-col gap-2 text-sm">
          {mine.length > 0 && (
            <div className="flex flex-col gap-1">
              <p className="font-medium">Suggested</p>
              <ul className="flex flex-col gap-1">
                {mine.map((s) => (
                  <li key={s.id} className="flex flex-wrap items-center gap-2">
                    <span>
                      {s.dossier_id ? nameOf(s.dossier_id) : `With ${s.identities.filter((i) => i.identity_key !== d.identity_key).map((i) => i.value_display).join(", ")}`}
                      {": "}
                      <SuggestionLine s={s} />
                    </span>
                    {s.dossier_id && <Button size="sm" variant="outline" onClick={() => setTarget(s.dossier_id!)}>Choose</Button>}
                    <Button size="sm" variant="ghost" onClick={() => reject(s)} disabled={busy}>Not the same person</Button>
                  </li>
                ))}
              </ul>
            </div>
          )}
          <label className="flex flex-col gap-1">
            Person
            <select className="rounded border bg-background px-2 py-1" value={target} onChange={(e) => setTarget(e.target.value)}>
              <option value="">Choose a person</option>
              {(people.data?.dossiers ?? []).map((p) => (
                <option key={p.id} value={p.id}>{p.display_name}</option>
              ))}
              <option value="new">A new person</option>
            </select>
          </label>
          {target === "new" && (
            <label className="flex flex-col gap-1">
              Name of the new person
              <input className="rounded border bg-background px-2 py-1" maxLength={255} value={newName} onChange={(e) => setNewName(e.target.value)} />
            </label>
          )}
          <label className="flex flex-col gap-1">
            Note (optional)
            <input className="rounded border bg-background px-2 py-1" maxLength={4000} value={note} onChange={(e) => setNote(e.target.value)} />
          </label>
          <p className="text-xs text-muted-foreground">Saved under your name with the standard reason: {standardReason(shown)}.</p>
          <div>
            <Button size="sm" onClick={link} disabled={!target || (target === "new" && !newName.trim()) || busy}>Link</Button>
          </div>
        </div>
      )}
      {done && <p role="status" className="text-sm">{done}</p>}
      {error && <p role="alert" className="text-sm">{error}</p>}
    </section>
  )
}
