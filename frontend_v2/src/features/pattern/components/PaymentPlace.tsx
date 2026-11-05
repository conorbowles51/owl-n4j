import { useEffect, useState } from "react"
import { patternAPI, type ManualPlace, type PlaceSuggestion, type PlaceSuggestions } from "../api"
import { PLACE_LABEL } from "@/features/map/lib/place-label"

const TOWN_RADIUS_M = "5000"
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

function errWords(e: unknown) {
  const status = (e as { status?: number })?.status
  if (status === 403) return "You can view this case but not change it."
  return e instanceof Error ? e.message : "That could not be saved."
}

/**
 * Attach a place to a payment (04 section 8.5): a map point and radius a person records, through the case decision
 * log with them as Actor. The payment itself is never changed; the place then counts as a payment place for that
 * whole day on the Patterns screen. Every earlier place stays listed with the decision that ended it. Where the
 * payment's own text names a town, the offline list offers it as a suggestion; using one only fills the point in, and
 * nothing is saved until the person writes why and saves.
 */
export function PaymentPlace({ caseId, transactionId }: { caseId?: string; transactionId: string }) {
  const ok = !!caseId && UUID.test(transactionId)
  const [items, setItems] = useState<ManualPlace[] | null>(null)
  const [failed, setFailed] = useState(false)
  const [open, setOpen] = useState<"attach" | "remove" | null>(null)
  const [lat, setLat] = useState("")
  const [lon, setLon] = useState("")
  const [radius, setRadius] = useState("100")
  const [reason, setReason] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [reload, setReload] = useState(0)
  const [offers, setOffers] = useState<PlaceSuggestions | null>(null)
  const [used, setUsed] = useState<PlaceSuggestion | null>(null)
  useEffect(() => {
    if (!ok || open !== "attach") return
    let live = true
    patternAPI.placeSuggestions(caseId!, transactionId)
      .then((d) => { if (live) setOffers(d) })
      .catch(() => { if (live) setOffers(null) })
    return () => { live = false }
  }, [ok, caseId, transactionId, open])
  useEffect(() => {
    if (!ok) return
    let live = true
    setFailed(false)
    patternAPI.manualPlaces(caseId!, transactionId)
      .then((d) => { if (live) setItems(d.items) })
      .catch(() => { if (live) setFailed(true) })
    return () => { live = false }
  }, [ok, caseId, transactionId, reload])
  if (!ok) return null
  const current = items?.find((p) => !p.removed_decision_id) ?? null
  const earlier = (items ?? []).filter((p) => p.removed_decision_id)
  const latN = Number(lat), lonN = Number(lon), radN = Number(radius)
  const valid = lat.trim() !== "" && lon.trim() !== "" && Number.isFinite(latN) && Number.isFinite(lonN) &&
    latN >= -90 && latN <= 90 && lonN >= -180 && lonN <= 180 && Number.isInteger(radN) && radN >= 1 && radN <= 50000
  const save = async () => {
    setBusy(true); setError(null)
    try {
      if (open === "attach") await patternAPI.attachPlace(caseId!, transactionId, latN, lonN, radN, reason.trim(), used)
      else await patternAPI.removePlace(caseId!, transactionId, reason.trim())
      setOpen(null); setReason(""); setUsed(null); setReload((n) => n + 1)
    } catch (e) { setError(errWords(e)) } finally { setBusy(false) }
  }
  return (
    <section aria-label="Place of this payment" className="text-sm">
      <h4 className="font-medium">Place of this payment</h4>
      {failed && <p className="text-muted-foreground">The place could not be read just now. The payment is unaffected.</p>}
      {items && !current && <p className="text-muted-foreground">No place attached. A statement does not say where a payment was made.</p>}
      {current && (
        <p>
          {current.lat.toFixed(5)}, {current.lon.toFixed(5)} within {current.radius_m.toLocaleString()} m, attached by{" "}
          {current.actor_name || "a person"}: “{current.reason}”. <span className="text-xs text-muted-foreground">{PLACE_LABEL}.</span>
        </p>
      )}
      {earlier.length > 0 && (
        <p className="text-xs text-muted-foreground">
          {earlier.length.toLocaleString()} earlier {earlier.length === 1 ? "place" : "places"} replaced or removed, kept in the decision log.
        </p>
      )}
      {items && open === null && (
        <p className="mt-1 flex gap-3">
          <button type="button" className="underline" onClick={() => setOpen("attach")}>{current ? "Change the place" : "Attach a place"}</button>
          {current && <button type="button" className="underline" onClick={() => setOpen("remove")}>Remove the place</button>}
        </p>
      )}
      {open && (
        <form className="mt-2 flex flex-col gap-2" onSubmit={(e) => { e.preventDefault(); void save() }}>
          {open === "attach" && offers && (offers.enabled ? offers.candidates.length > 0 : !!offers.reason) && (
            <div className="flex flex-col gap-1 text-xs" aria-label="Suggested places">
              {!offers.enabled && <p className="text-muted-foreground">{offers.reason}</p>}
              {offers.enabled && (
                <>
                  <p className="font-medium">{offers.label}{offers.total > offers.returned ? ` (${offers.returned.toLocaleString()} of ${offers.total.toLocaleString()} shown)` : ""}</p>
                  <ul className="flex flex-col gap-1">
                    {offers.candidates.map((c) => (
                      <li key={c.geonameid} className="flex flex-wrap items-baseline gap-2">
                        <span>{[c.name, c.admin1, c.country].filter(Boolean).join(", ")}</span>
                        <button type="button" className="underline" aria-pressed={used?.geonameid === c.geonameid} onClick={() => { setUsed(c); setLat(String(c.lat)); setLon(String(c.lon)); setRadius(TOWN_RADIUS_M) }}>Use this town</button>
                      </li>
                    ))}
                  </ul>
                  <p className="text-muted-foreground">{offers.words} {offers.attribution}</p>
                </>
              )}
            </div>
          )}
          {open === "attach" && (
            <div className="flex flex-wrap gap-2">
              <label className="flex flex-col text-xs">Latitude
                <input aria-label="Latitude" className="rounded border bg-background px-2 py-1" value={lat} onChange={(e) => { setUsed(null); setLat(e.target.value) }} inputMode="decimal" />
              </label>
              <label className="flex flex-col text-xs">Longitude
                <input aria-label="Longitude" className="rounded border bg-background px-2 py-1" value={lon} onChange={(e) => { setUsed(null); setLon(e.target.value) }} inputMode="decimal" />
              </label>
              <label className="flex flex-col text-xs">Radius (metres)
                <input aria-label="Radius (metres)" className="w-28 rounded border bg-background px-2 py-1" value={radius} onChange={(e) => setRadius(e.target.value)} inputMode="numeric" />
              </label>
            </div>
          )}
          <label className="flex flex-col text-xs">{open === "attach" ? "Why the payment was made here" : "Why the place is removed"}
            <textarea aria-label="Reason" className="rounded border bg-background px-2 py-1" value={reason} onChange={(e) => setReason(e.target.value)} rows={2} />
          </label>
          {open === "attach" && !valid && (lat || lon) && (
            <p className="text-xs text-destructive">Latitude is -90 to 90, longitude -180 to 180, the radius whole metres from 1 to 50,000.</p>
          )}
          {error && <p role="alert" className="text-xs text-destructive">{error}</p>}
          <p className="flex gap-2">
            <button type="submit" className="rounded border px-2 py-1" disabled={busy || !reason.trim() || (open === "attach" && !valid)}>
              {open === "attach" ? "Save the place" : "Remove"}
            </button>
            <button type="button" className="rounded border px-2 py-1" onClick={() => { setOpen(null); setError(null); setUsed(null) }}>Cancel</button>
          </p>
          <p className="text-xs text-muted-foreground">Recorded in the case decision log under your name. The payment itself is not changed.</p>
        </form>
      )}
    </section>
  )
}
