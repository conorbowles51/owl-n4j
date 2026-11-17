import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { setCurrentQuery } from "@/features/relations/api"
import { claimAPI, corroborateAPI, type ClaimWhat, type ClaimWhen, type ClaimWhere, type ClaimWho, type ParsedClaim } from "./api"
import { fromZoneInput, toZoneInput, type ClaimComposerRequest } from "./claim-composer"

const FIELD_WORDS = { who: "Who", when: "When", where: "Where", what: "What" } as const
const ACTIONS: Record<ClaimWhat["action"], string> = { presence: "was at a place", contact: "was in contact with", with: "was with" }

/**
 * Corroborate a free-text claim (lx-corrostatement C). The sentence is read into who, when, where and what, each shown
 * with the words it came from and marked "Read by Loupe · not confirmed". Nothing is weighed until the person confirms
 * or edits the chips; the confirmed claim is saved under their name with the sentence kept as written.
 */
export function ClaimComposer({ caseId, request, onClose }: { caseId: string; request: ClaimComposerRequest; onClose: () => void }) {
  const navigate = useNavigate()
  const [text, setText] = useState(request.text)
  const [stmt, setStmt] = useState(request.statementDate ?? "")
  const [speaker, setSpeaker] = useState(request.speaker ?? "")
  const [claim, setClaim] = useState<ParsedClaim | null>(null)
  const [who, setWho] = useState<ClaimWho[]>([])
  const [when, setWhen] = useState<ClaimWhen | null>(null)
  const [where, setWhere] = useState<ClaimWhere | null>(null)
  const [what, setWhat] = useState<ClaimWhat | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const read = async (sp = speaker) => {
    setBusy(true)
    setError(null)
    try {
      const got = (await claimAPI.parse(caseId, { text, ...(stmt ? { statement_date: stmt } : {}), ...(sp ? { speaker: sp } : {}), ...(request.source ? { source: request.source } : {}) })).claim
      setClaim(got)
      setWho(got.chips.who.value ?? [])
      setWhen(got.chips.when.status === "read" ? got.chips.when.value : null)
      setWhere(got.chips.where.status === "read" ? got.chips.where.value : null)
      setWhat(got.chips.what.status === "read" ? got.chips.what.value : null)
    } catch (e) {
      setError(e instanceof Error ? e.message : "The sentence could not be read.")
    } finally {
      setBusy(false)
    }
  }
  useEffect(() => { if (request.text) void read() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const confirmAndRun = async () => {
    if (!claim) return
    setBusy(true)
    setError(null)
    try {
      const wherePlace = where && where.lat != null && where.lon != null ? where : null
      const whatFinal = what && what.action !== "presence" && what.with.length === 0 ? { ...what, with: who.slice(1).map((w) => w.key) } : what
      await claimAPI.confirm(caseId, claim.id, { who, when, where: wherePlace, what: whatFinal, ...(!wherePlace && claim.chips.where.note ? { where_text: claim.chips.where.note } : {}) })
      const made = await corroborateAPI.run(caseId, { members: [{ type: "claim", id: claim.id, label: claim.sentence.slice(0, 120) }], surface: "corroborate", question: { kind: "statement", text: claim.sentence.slice(0, 200), chips: { claim_id: claim.id } } })
      setCurrentQuery(caseId, { id: made.group.id, count: made.group.member_count })
      onClose()
      navigate(`/cases/${caseId}/relations/${made.group.id}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Corroborate could not start. Nothing was weighed.")
    } finally {
      setBusy(false)
    }
  }
  const chip = (f: keyof typeof FIELD_WORDS) => claim?.chips[f]
  const header = (f: keyof typeof FIELD_WORDS) => {
    const c = chip(f)
    if (!c) return null
    return (
      <div className="text-xs text-muted-foreground">
        {c.status === "read" ? <>{c.read_by}{c.words ? <> · from “{c.words}”</> : null}{c.confidence ? <> · {c.confidence} confidence</> : null}</> : <span role="status">{c.note ?? `${FIELD_WORDS[f].toLowerCase()}: not stated`}</span>}
        {c.status === "read" && c.note ? <div>{c.note}</div> : null}
      </div>
    )
  }
  const addable = (claim?.people ?? []).filter((p) => !who.some((w) => w.key === p.key))
  return (
    <Dialog open onOpenChange={(o) => !o && !busy && onClose()}>
      <DialogContent className="max-h-[90vh] max-w-xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Corroborate this claim</DialogTitle>
          <DialogDescription>Loupe reads who, when, where and what from the sentence. Check each one, change what is wrong, then confirm. Nothing is weighed before you confirm.</DialogDescription>
        </DialogHeader>
        <label className="flex flex-col gap-1 text-sm">The claim
          <textarea aria-label="The claim" className="min-h-16 rounded border bg-card px-2 py-1 text-sm" value={text} onChange={(e) => { setText(e.target.value); setClaim(null) }} />
        </label>
        <div className="flex flex-wrap items-end gap-2 text-sm">
          <label className="flex flex-col gap-1">Date of the statement
            <input type="date" aria-label="Date of the statement" className="rounded border bg-card px-2 py-1" value={stmt} onChange={(e) => { setStmt(e.target.value); setClaim(null) }} />
          </label>
          <label className="flex flex-col gap-1">Who said it
            <select aria-label="Who said it" className="rounded border bg-card px-2 py-1" value={speaker} onChange={(e) => { setSpeaker(e.target.value); void read(e.target.value) }} disabled={!claim}>
              <option value="">Not given</option>
              {(claim?.people ?? []).map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
            </select>
          </label>
          <Button size="sm" variant="outline" disabled={busy || !text.trim()} onClick={() => void read()}>{claim ? "Read again" : busy ? "Reading…" : "Read the sentence"}</Button>
        </div>
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        {claim && (
          <div className="flex flex-col gap-3 text-sm">
            <section aria-label="Who" className="rounded border p-2">
              <strong>{FIELD_WORDS.who}</strong>
              {header("who")}
              <ul className="flex flex-wrap gap-1 pt-1">
                {who.map((w) => <li key={w.key} className="flex items-center gap-1 rounded border bg-muted px-2 py-0.5">{w.label}<button type="button" aria-label={`Remove ${w.label}`} className="px-1 text-muted-foreground" onClick={() => setWho(who.filter((x) => x.key !== w.key))}>×</button></li>)}
              </ul>
              {addable.length > 0 && <select aria-label="Add a person" className="mt-1 rounded border bg-card px-2 py-1" value="" onChange={(e) => { const p = addable.find((x) => x.key === e.target.value); if (p) setWho([...who, { key: p.key, label: p.label }]) }}><option value="">Add a person…</option>{addable.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}</select>}
            </section>
            <section aria-label="When" className="rounded border p-2">
              <strong>{FIELD_WORDS.when}</strong>
              {header("when")}
              <div className="flex flex-wrap items-center gap-2 pt-1">
                <input type="datetime-local" aria-label="From" className="rounded border bg-card px-2 py-1" value={when ? toZoneInput(when.start, when.zone) : ""} onChange={(e) => e.target.value && setWhen({ start: fromZoneInput(e.target.value, claim.zone), end: when?.end ?? fromZoneInput(e.target.value, claim.zone), zone: claim.zone, label: "" })} />
                <span>to</span>
                <input type="datetime-local" aria-label="To" className="rounded border bg-card px-2 py-1" value={when ? toZoneInput(when.end, when.zone) : ""} onChange={(e) => e.target.value && setWhen({ start: when?.start ?? fromZoneInput(e.target.value, claim.zone), end: fromZoneInput(e.target.value, claim.zone), zone: claim.zone, label: "" })} />
                <span className="text-muted-foreground">({claim.zone})</span>
              </div>
            </section>
            <section aria-label="Where" className="rounded border p-2">
              <strong>{FIELD_WORDS.where}</strong>
              {header("where")}
              <div className="flex flex-wrap items-center gap-2 pt-1">
                <input aria-label="Latitude" placeholder="Latitude" inputMode="decimal" className="w-28 rounded border bg-card px-2 py-1" value={where?.lat ?? ""} onChange={(e) => setWhere({ ...(where ?? { name: claim.chips.where.words ?? "" }), lat: e.target.value === "" ? undefined : Number(e.target.value), radius_m: where?.radius_m ?? 150 })} />
                <input aria-label="Longitude" placeholder="Longitude" inputMode="decimal" className="w-28 rounded border bg-card px-2 py-1" value={where?.lon ?? ""} onChange={(e) => setWhere({ ...(where ?? { name: claim.chips.where.words ?? "" }), lon: e.target.value === "" ? undefined : Number(e.target.value), radius_m: where?.radius_m ?? 150 })} />
                <input aria-label="Radius in metres" placeholder="Radius (m)" inputMode="decimal" className="w-24 rounded border bg-card px-2 py-1" value={where?.radius_m ?? ""} onChange={(e) => setWhere({ ...(where ?? { name: "" }), radius_m: Number(e.target.value) || undefined })} />
                {where && <button type="button" className="text-muted-foreground underline" onClick={() => setWhere(null)}>No place</button>}
              </div>
              {!where?.lat && <p className="pt-1 text-xs text-muted-foreground">Without a place with a position, a claim about where someone was reads Can't tell.</p>}
            </section>
            <section aria-label="What" className="rounded border p-2">
              <strong>{FIELD_WORDS.what}</strong>
              {header("what")}
              <div className="flex flex-wrap items-center gap-2 pt-1">
                <select aria-label="What was said" className="rounded border bg-card px-2 py-1" value={what?.action ?? ""} onChange={(e) => setWhat({ action: e.target.value as ClaimWhat["action"], negated: what?.negated ?? false, with: what?.with ?? [] })}>
                  {!what && <option value="">Choose…</option>}
                  {Object.entries(ACTIONS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
                <label className="flex items-center gap-1"><input type="checkbox" checked={what?.negated ?? false} onChange={(e) => what && setWhat({ ...what, negated: e.target.checked })} />said it did not happen</label>
                {what && what.action !== "presence" && <span className="text-muted-foreground">with {what.with.map((k) => claim.people.find((p) => p.key === k)?.label ?? k).join(", ") || "no one named: remove the claimant from Who and add the other person"}</span>}
              </div>
            </section>
          </div>
        )}
        <DialogFooter className="gap-2">
          <Button disabled={busy || !claim || who.length === 0 || !what} onClick={() => void confirmAndRun()}>{busy ? "Working…" : "Confirm and corroborate"}</Button>
          <Button variant="ghost" onClick={onClose} disabled={busy}>Cancel</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
