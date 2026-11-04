import { lazy, Suspense, useState } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import {
  textPlacesAPI, type Suggestion, type SuggestionList, type TextPlace, type TextPlaceHistoryRow,
} from "../text-places-api"
import { startRadiusFor, suggestionWords, validPlacement } from "../text-places-lib"

const TextPlacePicker = lazy(() => import("./TextPlacePicker"))

function errWords(e: unknown) {
  const status = (e as { status?: number })?.status
  if (status === 403) return "You can view this case but not change it."
  return e instanceof Error ? e.message : "That could not be saved."
}

function when(iso: string | null) {
  if (!iso) return "no time recorded"
  return new Date(iso).toISOString().replace("T", " ").slice(0, 16) + " UTC"
}

/**
 * Text places (04 section 6.5): written places on this phone's records that carry no coordinate (a calendar
 * location, a check-in's place name, a written address). Each is placed on the map only by a person, with a point,
 * radius and reason recorded in the case decision log under their name. Suggestions from the offline place list are
 * shown as suggestions and never saved by themselves. A placed text counts as planned or declared, never as the
 * phone being there.
 */
export function TextPlaces({ caseId, extractionIds }: { caseId: string; extractionIds: string[] }) {
  if (!extractionIds.length) return null
  return (
    <section aria-label="Text places" className="flex flex-col gap-2 rounded border p-3 text-sm">
      <h3 className="font-medium">Text places</h3>
      <p className="text-xs text-muted-foreground">
        Places written on records with no position. They are placed on the map only by a person; a placed text shows
        what the record points to (planned or declared), never that the phone was there.
      </p>
      {extractionIds.map((e) => <TextPlaceList key={e} caseId={caseId} extractionId={e} />)}
    </section>
  )
}

function TextPlaceList({ caseId, extractionId }: { caseId: string; extractionId: string }) {
  const [cursor, setCursor] = useState(0)
  const q = useQuery({ queryKey: ["text-places", caseId, extractionId, cursor],
    queryFn: () => textPlacesAPI.list(caseId, extractionId, cursor) })
  if (q.isLoading) return <p className="text-muted-foreground">Reading text places…</p>
  if (q.isError || !q.data) return <p className="text-muted-foreground">Text places could not be read just now.</p>
  const d = q.data
  if (!d.total) return <p className="text-muted-foreground">No text places without a position on this phone.</p>
  return (
    <div className="flex flex-col gap-2">
      <p>
        {d.total.toLocaleString()} text {d.total === 1 ? "place" : "places"}: {d.counts.placed.toLocaleString()} placed by a person,{" "}
        {d.counts.not_placed.toLocaleString()} not placed.{" "}
        {d.returned < d.total && <>Showing {(d.cursor + 1).toLocaleString()} to {(d.cursor + d.returned).toLocaleString()}.</>}
      </p>
      <p className="text-xs text-muted-foreground" data-testid="suggestion-status">{d.suggestions.reason}</p>
      <ul className="flex flex-col gap-2">
        {d.items.map((t) => (
          <TextPlaceRow key={`${t.record_uid}|${t.field_path}|${t.placement?.id ?? "none"}`} caseId={caseId} item={t} suggestionsOn={d.suggestions.enabled} />
        ))}
      </ul>
      {(d.cursor > 0 || d.next_cursor != null) && (
        <p className="flex gap-3">
          {d.cursor > 0 && <button type="button" className="underline" onClick={() => setCursor(Math.max(0, d.cursor - d.limit))}>Previous</button>}
          {d.next_cursor != null && <button type="button" className="underline" onClick={() => setCursor(d.next_cursor!)}>Next</button>}
        </p>
      )}
    </div>
  )
}

function TextPlaceRow({ caseId, item, suggestionsOn }: { caseId: string; item: TextPlace; suggestionsOn: boolean }) {
  const qc = useQueryClient()
  const p = item.placement
  const [open, setOpen] = useState<"place" | "remove" | null>(null)
  const [lat, setLat] = useState(p ? String(p.lat) : "")
  const [lon, setLon] = useState(p ? String(p.lon) : "")
  const [radius, setRadius] = useState(p ? String(Math.round(p.radius_m)) : "500")
  const [reason, setReason] = useState("")
  const [chosen, setChosen] = useState<Suggestion | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showHistory, setShowHistory] = useState(false)
  const [sugg, setSugg] = useState<SuggestionList | null>(null)
  const [suggFailed, setSuggFailed] = useState(false)
  const valid = validPlacement(lat, lon, radius)
  const loadSuggestions = async () => {
    setSuggFailed(false)
    try { setSugg(await textPlacesAPI.suggestions(caseId, item.record_uid, item.field_path)) } catch { setSuggFailed(true) }
  }
  const startFrom = (s: Suggestion) => {
    setChosen(s); setLat(String(s.lat)); setLon(String(s.lon)); setRadius(String(startRadiusFor(s.population)))
  }
  const save = async () => {
    setBusy(true); setError(null)
    try {
      if (open === "place") {
        const la = Number(lat), lo = Number(lon)
        // the suggestion is kept beside the placement only when the point is still the one it offered
        const keep = chosen && Number(chosen.lat) === la && Number(chosen.lon) === lo ? chosen : null
        await textPlacesAPI.place(caseId, { record_uid: item.record_uid, field_path: item.field_path, lat: la, lon: lo,
          radius_m: Number(radius), reason: reason.trim(), suggestion: keep })
      } else {
        await textPlacesAPI.remove(caseId, { record_uid: item.record_uid, field_path: item.field_path, reason: reason.trim() })
      }
      setOpen(null); setReason("")
      await qc.invalidateQueries({ queryKey: ["text-places", caseId] })
      await qc.invalidateQueries({ queryKey: ["text-place-history", caseId, item.record_uid, item.field_path] })
      await qc.invalidateQueries({ queryKey: ["pattern-places", caseId] })
    } catch (e) { setError(errWords(e)) } finally { setBusy(false) }
  }
  return (
    <li className="flex flex-col gap-1 rounded border p-2" aria-label={`${item.group_words}: ${item.place_text}`}>
      <p>
        <span className="font-medium">{item.group_words}</span>{" "}
        <span className="text-xs text-muted-foreground">({item.kind_words}, {when(item.start_utc)})</span>
      </p>
      <p className="break-words">“{item.place_text}”</p>
      {item.corrected && (
        <p className="text-xs text-muted-foreground">Corrected by a person. The phone recorded: “{item.phone_text}”.</p>
      )}
      {p ? (
        <p>
          Placed at {p.lat.toFixed(5)}, {p.lon.toFixed(5)} within {Math.round(p.radius_m).toLocaleString()} m by{" "}
          {p.actor_name || "a person"} on {when(p.created_at)}: “{p.reason}”.
          {p.suggestion && <span className="text-xs text-muted-foreground"> Started from the suggestion {suggestionWords(p.suggestion)}.</span>}
          {p.place_text !== item.place_text && (
            <span className="text-xs text-muted-foreground"> The text read “{p.place_text}” when it was placed.</span>
          )}
        </p>
      ) : (
        <p className="text-muted-foreground">Not placed. Nothing on the map comes from this text until a person places it.</p>
      )}
      {open === null && (
        <p className="flex flex-wrap gap-3">
          <button type="button" className="underline" onClick={() => { setOpen("place"); if (suggestionsOn && !sugg) void loadSuggestions() }}>
            {p ? "Change the place" : "Place on map"}
          </button>
          {p && <button type="button" className="underline" onClick={() => setOpen("remove")}>Remove the place</button>}
          {item.decisions > 0 && (
            <button type="button" className="underline" onClick={() => setShowHistory((v) => !v)}>
              {showHistory ? "Hide decisions" : `Decisions (${item.decisions.toLocaleString()})`}
            </button>
          )}
        </p>
      )}
      {showHistory && <TextPlaceHistory caseId={caseId} item={item} />}
      {open && (
        <form className="mt-1 flex flex-col gap-2" onSubmit={(e) => { e.preventDefault(); void save() }}>
          {open === "place" && (
            <>
              {suggestionsOn && (
                <div aria-label="Suggestions" className="flex flex-col gap-1">
                  {suggFailed && <p className="text-xs text-muted-foreground">Suggestions could not be read just now.</p>}
                  {sugg && !sugg.enabled && <p className="text-xs text-muted-foreground">{sugg.reason}</p>}
                  {sugg?.enabled && sugg.total === 0 && <p className="text-xs text-muted-foreground">The offline place list has no town named in this text.</p>}
                  {sugg?.enabled && sugg.total > 0 && (
                    <>
                      <p className="text-xs">
                        Suggested, not confirmed: {sugg.returned < sugg.total
                          ? `${sugg.returned.toLocaleString()} of ${sugg.total.toLocaleString()} places with a name in this text`
                          : `${sugg.total.toLocaleString()} ${sugg.total === 1 ? "place" : "places"} with a name in this text`}.
                        Choosing one only fills in the point; you set the radius and save.
                      </p>
                      <p className="flex flex-wrap gap-1">
                        {sugg.candidates.map((s) => (
                          <button key={String(s.geonameid)} type="button" aria-pressed={chosen?.geonameid === s.geonameid}
                            className={`rounded-full border border-dashed px-2 py-0.5 text-xs ${chosen?.geonameid === s.geonameid ? "bg-muted" : ""}`}
                            onClick={() => startFrom(s)}>
                            {suggestionWords(s)} · suggested
                          </button>
                        ))}
                      </p>
                      {sugg.attribution && <p className="text-[11px] text-muted-foreground">{sugg.attribution}</p>}
                    </>
                  )}
                </div>
              )}
              <Suspense fallback={<p className="text-xs text-muted-foreground">Opening the map…</p>}>
                <TextPlacePicker
                  point={valid ? { lat: Number(lat), lon: Number(lon) } : null}
                  radiusM={Number(radius) || 0}
                  suggestions={(sugg?.candidates ?? []).map((s) => ({ lat: Number(s.lat), lon: Number(s.lon), name: s.name }))}
                  onPick={(pt) => { setLat(String(pt.lat)); setLon(String(pt.lon)) }}
                />
              </Suspense>
              <div className="flex flex-wrap gap-2">
                <label className="flex flex-col text-xs">Latitude
                  <input aria-label="Latitude" className="rounded border bg-background px-2 py-1" value={lat} onChange={(e) => setLat(e.target.value)} inputMode="decimal" />
                </label>
                <label className="flex flex-col text-xs">Longitude
                  <input aria-label="Longitude" className="rounded border bg-background px-2 py-1" value={lon} onChange={(e) => setLon(e.target.value)} inputMode="decimal" />
                </label>
                <label className="flex flex-col text-xs">Radius (metres)
                  <input aria-label="Radius (metres)" className="w-28 rounded border bg-background px-2 py-1" value={radius} onChange={(e) => setRadius(e.target.value)} inputMode="numeric" />
                </label>
              </div>
              {!valid && (lat || lon) && (
                <p className="text-xs text-destructive">Latitude is -90 to 90, longitude -180 to 180, the radius whole metres from 1 to 50,000.</p>
              )}
            </>
          )}
          <label className="flex flex-col text-xs">{open === "place" ? "Why the place is here" : "Why the place is removed"}
            <textarea aria-label="Reason" className="rounded border bg-background px-2 py-1" value={reason} onChange={(e) => setReason(e.target.value)} rows={2} />
          </label>
          {error && <p role="alert" className="text-xs text-destructive">{error}</p>}
          <p className="flex gap-2">
            <button type="submit" className="rounded border px-2 py-1" disabled={busy || !reason.trim() || (open === "place" && !valid)}>
              {open === "place" ? "Save the place" : "Remove"}
            </button>
            <button type="button" className="rounded border px-2 py-1" onClick={() => { setOpen(null); setError(null) }}>Cancel</button>
          </p>
          <p className="text-xs text-muted-foreground">Recorded in the case decision log under your name. The phone record is not changed.</p>
        </form>
      )}
    </li>
  )
}

function TextPlaceHistory({ caseId, item }: { caseId: string; item: TextPlace }) {
  const q = useQuery({ queryKey: ["text-place-history", caseId, item.record_uid, item.field_path],
    queryFn: () => textPlacesAPI.history(caseId, item.record_uid, item.field_path) })
  if (q.isLoading) return <p className="text-xs text-muted-foreground">Reading decisions…</p>
  if (!q.data) return <p className="text-xs text-muted-foreground">The decisions could not be read just now.</p>
  return (
    <ol aria-label="Decisions" className="ml-4 list-decimal text-xs">
      {q.data.items.map((h: TextPlaceHistoryRow) => (
        <li key={h.id}>
          {when(h.created_at)}, {h.actor_name || "a person"}: {h.lat.toFixed(5)}, {h.lon.toFixed(5)} within{" "}
          {Math.round(h.radius_m).toLocaleString()} m, “{h.reason}”. Text then: “{h.place_text}”.{" "}
          {!h.removed_decision_id ? "Current." : h.ended_by === "remove_text_place"
            ? `Removed on ${when(h.ended_at ?? null)} by ${h.ended_actor_name || "a person"}: “${h.ended_reason ?? ""}”.`
            : "Replaced by the next placement."}
        </li>
      ))}
    </ol>
  )
}
