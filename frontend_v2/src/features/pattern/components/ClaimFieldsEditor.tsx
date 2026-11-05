import { lazy, Suspense, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { patternAPI, type Claim, type ClaimKind, type PickedIdentity, type RoutinePlaceRow, type Subject } from "../api"
import { counterpartWords, isContactKind, isPlaceKind, isSubjectKind, KIND_WORDS, type ClaimInput } from "../claim-form-lib"
import { errorWords } from "../lanes-lib"
import { placeName } from "@/features/map/lib/places-geo"

const TextPlacePicker = lazy(() => import("./TextPlacePicker"))
const INPUT = "rounded border bg-background px-2 py-1"

/**
 * The fields of a statement, shared by entering one and editing one (04 section 9.1): the words, the window, the
 * tolerance on "not using the phone", the place (a routine place of this phone or person, a point on the map, or
 * typed coordinates) and the other person (a phone or person of the case, or for contact an identity found by search).
 * `drafted` is what the model wrote; it is shown beside the field a person settles and is never written over.
 */
export function ClaimFieldsEditor({ caseId, subject, value, onChange, drafted, focus }: {
  caseId: string
  subject: Subject
  value: ClaimInput
  onChange: (v: ClaimInput) => void
  drafted?: Claim["as_drafted"]
  focus?: string
}) {
  const set = (patch: Partial<ClaimInput>) => onChange({ ...value, ...patch })
  return (
    <div className="mt-2 grid grid-cols-1 gap-2 md:grid-cols-2">
      <label className="flex flex-col">What the statement says
        <select value={value.kind} onChange={(e) => set({ kind: e.target.value as ClaimKind, counterpart: null })} className={INPUT}>
          {Object.entries(KIND_WORDS).map(([k, w]) => <option key={k} value={k}>{w}</option>)}
        </select></label>
      <label className="flex flex-col">The statement's own words<input value={value.words} onChange={(e) => set({ words: e.target.value })} className={INPUT} /></label>
      <label className="flex flex-col">From (UTC)<input autoFocus={focus === "window_start"} type="datetime-local" value={value.start} onChange={(e) => set({ start: e.target.value })} className={INPUT} /></label>
      <label className="flex flex-col">Until (UTC)<input autoFocus={focus === "window_end"} type="datetime-local" value={value.end} onChange={(e) => set({ end: e.target.value })} className={INPUT} /></label>
      <label className="flex flex-col">Zone the statement uses<input autoFocus={focus === "window_zone"} placeholder="For example Europe/Dublin or UTC" value={value.zone} onChange={(e) => set({ zone: e.target.value })} className={INPUT} /></label>
      {value.kind === "inactive" && (
        <label className="flex flex-col">Minutes of use to allow at each end
          <input type="number" min={0} max={120} step={1} value={value.tolerance} onChange={(e) => set({ tolerance: e.target.value })} className={INPUT} />
          <span className="text-xs text-muted-foreground">Use this close to the start or end is listed as context, not against the statement: "asleep by about eleven" is not undercut by a message at 23:05 if you allow 10 minutes. 0 to 120.</span>
        </label>
      )}
      {isPlaceKind(value.kind) && <PlaceFields caseId={caseId} subject={subject} value={value} set={set} drafted={drafted?.place_text} focus={focus === "place"} />}
      {(isSubjectKind(value.kind) || isContactKind(value.kind)) && <CounterpartFields caseId={caseId} subject={subject} value={value} set={set} drafted={drafted?.counterpart_text} focus={focus === "counterpart"} />}
    </div>
  )
}

function placeOption(p: RoutinePlaceRow) {
  const name = placeName(p)
  return `${name}: ${p.day_count.toLocaleString("en-US")} days, within ${Math.round(p.radius_m).toLocaleString("en-US")} m${p.routine ? "" : " (not part of the routine)"}`
}

function PlaceFields({ caseId, subject, value, set, drafted, focus }: {
  caseId: string; subject: Subject; value: ClaimInput; set: (p: Partial<ClaimInput>) => void; drafted?: string | null; focus: boolean
}) {
  const [map, setMap] = useState(false)
  const routine = useQuery({ queryKey: ["pattern-routine", caseId, JSON.stringify(subject)], queryFn: () => patternAPI.routine(caseId, subject) })
  const places = routine.data?.places ?? []
  function pick(id: string) {
    const p = places.find((x) => String(x.cluster_id) === id)
    if (!p) { set({ clusterId: null, placeLabel: "", lat: "", lon: "" }); return }
    set({ clusterId: p.cluster_id, placeLabel: p.label ?? "", lat: String(p.lat), lon: String(p.lon), radius: String(Math.max(1, Math.round(p.radius_m))) })
  }
  const typed = (patch: Partial<ClaimInput>) => set({ ...patch, clusterId: null, placeLabel: "" })
  const lat = Number(value.lat), lon = Number(value.lon)
  const point = value.lat.trim() && value.lon.trim() && Number.isFinite(lat) && Number.isFinite(lon) ? { lat, lon } : null
  return (
    <div className="flex flex-col gap-1 md:col-span-2">
      {drafted && <p className="text-xs">The draft says: "{drafted}". Say where that is before confirming.</p>}
      <label className="flex flex-col">A routine place of this phone or person
        <select autoFocus={focus} value={value.clusterId ?? ""} onChange={(e) => pick(e.target.value)} className={INPUT}>
          <option value="">Choose a place…</option>
          {places.map((p) => <option key={p.cluster_id} value={p.cluster_id}>{placeOption(p)}</option>)}
        </select></label>
      {routine.isError && <p className="text-xs">The routine places could not be read: {errorWords(routine.error)} Set a point instead.</p>}
      {routine.isSuccess && places.length === 0 && <p className="text-xs">No routine places on this phone or person yet. Set a point instead.</p>}
      <div className="flex flex-wrap items-center gap-1">
        <input aria-label="Latitude" placeholder="Latitude" value={value.lat} onChange={(e) => typed({ lat: e.target.value })} className={`w-24 ${INPUT}`} />
        <input aria-label="Longitude" placeholder="Longitude" value={value.lon} onChange={(e) => typed({ lon: e.target.value })} className={`w-24 ${INPUT}`} />
        <input aria-label="Radius in metres" value={value.radius} onChange={(e) => typed({ radius: e.target.value })} className={`w-20 ${INPUT}`} />
        <button type="button" className="text-xs underline" onClick={() => setMap(!map)}>{map ? "Hide the map" : "Place on map"}</button>
      </div>
      {map && (
        <Suspense fallback={<p className="text-xs text-muted-foreground">Opening the map…</p>}>
          <TextPlacePicker point={point} radiusM={Number(value.radius) || 0} suggestions={[]} onPick={(p) => typed({ lat: String(p.lat), lon: String(p.lon) })} />
        </Suspense>
      )}
    </div>
  )
}

function identityLine(i: PickedIdentity) {
  const name = i.person?.display_name || i.names[0]?.name
  return `${name ? `${name}, ` : ""}${i.value_display ?? i.identity_key} (${i.event_count.toLocaleString("en-US")} events)`
}

function CounterpartFields({ caseId, subject, value, set, drafted, focus }: {
  caseId: string; subject: Subject; value: ClaimInput; set: (p: Partial<ClaimInput>) => void; drafted?: string | null; focus: boolean
}) {
  const list = useQuery({ queryKey: ["pattern-subjects", caseId], queryFn: () => patternAPI.subjects(caseId) })
  const contact = isContactKind(value.kind)
  const me = JSON.stringify(subject)
  const options = [
    ...(contact ? [] : (list.data?.extractions ?? []).map((e) => ({ s: { kind: "extraction", extraction_id: e.extraction_id } as Subject, label: e.label }))),
    ...(list.data?.dossiers ?? []).map((d) => ({ s: { kind: "dossier", dossier_id: d.dossier_id } as Subject, label: `${d.name} (person)` })),
  ].filter((o) => JSON.stringify(o.s) !== me)
  const chosen = value.counterpart && !("identity_ids" in value.counterpart) ? JSON.stringify(value.counterpart) : ""
  return (
    <div className="flex flex-col gap-1 md:col-span-2">
      {drafted && <p className="text-xs">The draft says: "{drafted}". Choose who that is before confirming.</p>}
      <label className="flex flex-col">{contact ? "The other person" : "The other phone or person"}
        <select autoFocus={focus} value={chosen} onChange={(e) => set({ counterpart: e.target.value ? JSON.parse(e.target.value) as Subject : null })} className={INPUT}>
          <option value="">Choose…</option>
          {options.map((o) => <option key={JSON.stringify(o.s)} value={JSON.stringify(o.s)}>{o.label}</option>)}
        </select></label>
      {list.isSuccess && options.length === 0 && !contact && <p className="text-xs">This case has no other phone or person to choose.</p>}
      {contact && <IdentitySearch caseId={caseId} value={value} set={set} />}
      {value.counterpart && <p className="text-xs">Chosen: {counterpartWords(value.counterpart, list.data)}</p>}
    </div>
  )
}

function IdentitySearch({ caseId, value, set }: { caseId: string; value: ClaimInput; set: (p: Partial<ClaimInput>) => void }) {
  const [q, setQ] = useState("")
  const [found, setFound] = useState<{ items: PickedIdentity[]; total: number } | null>(null)
  const [err, setErr] = useState<string | null>(null)
  async function search() {
    setErr(null)
    try { setFound(await patternAPI.identities(caseId, q.trim())) } catch (e) { setErr(errorWords(e)) }
  }
  return (
    <div className="flex flex-col gap-1">
      <div className="flex flex-wrap items-center gap-1">
        <input aria-label="Find a name or number" placeholder="Or find a name or number" value={q} onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); void search() } }} className={INPUT} />
        <Button type="button" size="sm" variant="outline" onClick={search}>Find</Button>
      </div>
      {err && <p role="alert" className="text-destructive">{err}</p>}
      {found && (
        <>
          <p className="text-xs">{found.items.length === found.total ? `${found.total.toLocaleString("en-US")} found.` : `Showing ${found.items.length.toLocaleString("en-US")} of ${found.total.toLocaleString("en-US")} found, most events first. Search again to narrow them.`}</p>
          <ul className="flex flex-col gap-0.5">
            {found.items.map((i) => (
              <li key={i.identity_id}><button type="button" className="text-left text-xs underline"
                onClick={() => set({ counterpart: { identity_ids: [i.identity_id], label: identityLine(i) } })}>{identityLine(i)}</button></li>
            ))}
          </ul>
        </>
      )}
      {value.counterpart && "identity_ids" in value.counterpart && <button type="button" className="self-start text-xs underline" onClick={() => set({ counterpart: null })}>Clear the choice</button>}
    </div>
  )
}
