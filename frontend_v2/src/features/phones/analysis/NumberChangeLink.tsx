import { useState } from "react"
import { Link } from "react-router-dom"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { dossiersAPI } from "@/features/dossiers/api"
import { errorWords, identitiesAPI } from "../review/identities.api"

const PERSON = "person:"

/**
 * Link the two sides of a possible number change to one person (05 16c.3 step 4, 16c.4), through the identity-link
 * decision of 02 8.8: saved under the name of the person who clicks, with the standard reason, reversible from Needs
 * a decision. A side that is already a reviewed person stays that person; nothing moves an existing link.
 */
export function NumberChangeLink({ caseId, from, to, fromDisplay, toDisplay }: { caseId: string; from: string; to: string; fromDisplay: string; toDisplay: string }) {
  const [open, setOpen] = useState(false)
  if (!open) return <Button size="sm" variant="outline" className="ml-2 h-6 px-2 text-xs" onClick={() => setOpen(true)}>Link these two to one person…</Button>
  return <Panel caseId={caseId} sides={[from, to]} words={`${fromDisplay} and ${toDisplay}`} onClose={() => setOpen(false)} />
}

function Panel({ caseId, sides, words, onClose }: { caseId: string; sides: string[]; words: string; onClose: () => void }) {
  const client = useQueryClient()
  const keys = sides.filter((s) => !s.startsWith(PERSON))
  const pair = useQuery({ queryKey: ["phone-identity-pair", caseId, keys], queryFn: () => identitiesAPI.pair(caseId, keys), enabled: keys.length > 0 })
  const people = useQuery({ queryKey: ["dossiers", caseId, "phone-link"], queryFn: () => dossiersAPI.list({ caseId, limit: 200 }) })
  const [target, setTarget] = useState("")
  const [newName, setNewName] = useState("")
  const [note, setNote] = useState("")
  const [done, setDone] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const nameOf = (id: string) => people.data?.dossiers.find((p) => p.id === id)?.display_name ?? pair.data?.items.find((i) => i.linked_dossier?.id === id)?.linked_dossier?.name ?? "a person"
  const review = <Link className="underline" to={`/cases/${encodeURIComponent(caseId)}/phone-review`}>Needs a decision</Link>
  const wrap = (body: React.ReactNode) => (
    <div className="mt-1 flex flex-col gap-1 rounded border p-2 text-xs" aria-label="Link these two to one person">
      {body}
      <Button size="sm" variant="ghost" className="self-start" onClick={onClose}>Close</Button>
    </div>
  )
  if (keys.length && pair.isError) return wrap(<p role="alert">{errorWords(pair.error)}</p>)
  if (keys.length && !pair.data) return wrap(<p role="status">Loading the two identities.</p>)
  const items = pair.data?.items ?? []
  const held = [...new Set([...sides.filter((s) => s.startsWith(PERSON)).map((s) => s.slice(PERSON.length)), ...items.flatMap((i) => (i.linked_dossier ? [i.linked_dossier.id] : []))])]
  if (done) return wrap(<p role="status">{done} The decision is under your name; unlink it in {review}.</p>)
  if (items.some((i) => !i.can_be_a_person)) return wrap(<p>A group conversation is not a person, so these two cannot be linked to one.</p>)
  if (held.length > 1) return wrap(<p>These two are already linked to different people: {held.map(nameOf).join(" and ")}. Nothing moves an existing link; unlink one in {review} first.</p>)
  if (!items.some((i) => !i.linked_dossier)) return wrap(<p role="status">Both are already {held.length ? nameOf(held[0]) : "one person"}.</p>)
  const chosen = held[0] ?? target
  const save = async () => {
    setBusy(true)
    setError(null)
    try {
      await identitiesAPI.decide(caseId, {
        decision: "link_phone_identity", identity_keys: keys, reasons_shown: [{ reason: "number_change" }],
        ...(chosen === "new" ? { new_person_name: newName.trim() } : { dossier_id: chosen }),
        note: note.trim() || undefined, expected_revision: pair.data?.expected_revision,
      })
      setDone(`Linked ${words} to ${chosen === "new" ? newName.trim() : nameOf(chosen)}.`)
      await client.invalidateQueries({ queryKey: ["dossiers", caseId] })
    } catch (e) {
      setError(errorWords(e))
    } finally {
      await client.invalidateQueries({ queryKey: ["phone-identity-pair", caseId, keys] })
      setBusy(false)
    }
  }
  return wrap(
    <>
      <p>Linking says {words} are one person. It is your decision, saved under your name; this list only says they might be.</p>
      {held.length ? <p>The other side is already {nameOf(held[0])}, so this joins it to them.</p> : (
        <label className="flex flex-col gap-0.5">Person
          <select className="rounded border bg-background p-1" value={target} onChange={(e) => setTarget(e.target.value)}>
            <option value="">Choose a person</option>
            {(people.data?.dossiers ?? []).map((p) => <option key={p.id} value={p.id}>{p.display_name}</option>)}
            <option value="new">A new person</option>
          </select>
        </label>
      )}
      {chosen === "new" && (
        <label className="flex flex-col gap-0.5">Name of the new person
          <input className="rounded border bg-background p-1" maxLength={255} value={newName} onChange={(e) => setNewName(e.target.value)} />
        </label>
      )}
      <label className="flex flex-col gap-0.5">Note (optional)
        <input className="rounded border bg-background p-1" maxLength={4000} value={note} onChange={(e) => setNote(e.target.value)} />
      </label>
      {error && <p role="alert">{error}</p>}
      <Button size="sm" className="self-start" disabled={busy || !chosen || (chosen === "new" && !newName.trim())} onClick={() => void save()}>Link</Button>
    </>)
}
