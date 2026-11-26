import { useEffect, useState } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { useMediaQuery } from "@/hooks/use-media-query"
import { clearSelection, removePart, selectionCount, useSelection } from "./selection-store"
import { corroborateHref, forgetCorroborateRequest } from "@/features/leads/open"
import { PasteList } from "./PasteList"
import { SavedSubsets } from "./SavedSubsets"
import { ClaimComposer } from "./ClaimComposer"
import { CLAIM_EVENT, type ClaimComposerRequest } from "./claim-composer"

/**
 * The selection tray (lx-corroselect B): every part of the case-wide selection as a removable chip with its count and
 * the screen it came from, the whole count, and the way to the Corroborate page. It follows the investigator.
 * Below md it is a one-line strip in the page's own flow, above the bottom bar: the page ends above it instead of under
 * it (a floating tray covered the agent's message box at 390 px), and "More" opens the rest over the page.
 */
export function CorroborateTray() {
  const { id: caseId } = useParams()
  const parts = useSelection(caseId)
  const navigate = useNavigate()
  const [paste, setPaste] = useState(false)
  const [saved, setSaved] = useState(false)
  const [claim, setClaim] = useState<ClaimComposerRequest | null>(null)
  const narrow = useMediaQuery("(max-width: 767px)")
  const [more, setMore] = useState(false)
  useEffect(() => {
    const open = (e: Event) => setClaim((e as CustomEvent<ClaimComposerRequest>).detail)
    window.addEventListener(CLAIM_EVENT, open)
    return () => window.removeEventListener(CLAIM_EVENT, open)
  }, [])
  if (!caseId) return null
  const total = selectionCount(parts)
  // Corroborate opens the Corroborate page with the question filled from the whole selection (lx-corroredo A)
  const ask = () => { forgetCorroborateRequest(caseId); navigate(corroborateHref(caseId, { from: "tray" })) }
  const dialogs = (
    <>
      {paste && <PasteList caseId={caseId} onClose={() => setPaste(false)} onDone={() => { setPaste(false); if (!parts.length) ask() }} />}
      {saved && <SavedSubsets caseId={caseId} onClose={() => setSaved(false)} />}
      {claim && <ClaimComposer caseId={caseId} request={claim} onClose={() => setClaim(null)} />}
    </>
  )
  if (narrow)
    return (
      <>
        <div role="region" aria-label="Corroborate selection" data-guide="corroborate-tray" className="relative flex h-10 shrink-0 items-center gap-3 border-t bg-background px-3 text-sm">
          {parts.length ? (
            <>
              <strong className="truncate">{total.toLocaleString("en-US")} {total === 1 ? "item" : "items"} selected</strong>
              <Button size="sm" onClick={() => ask()} data-guide="corroborate-run">Corroborate</Button>
              <button type="button" className="ml-auto text-muted-foreground underline" aria-expanded={more} onClick={() => setMore(!more)}>{more ? "Less" : "More"}</button>
            </>
          ) : (
            <>
              <button type="button" className="text-muted-foreground underline" onClick={() => setPaste(true)} data-guide="corroborate-paste">Paste a list</button>
              <button type="button" className="text-muted-foreground underline" onClick={() => setSaved(true)} data-guide="corroborate-saved">Saved subsets</button>
              <button type="button" className="text-muted-foreground underline" onClick={() => setClaim({ text: "" })} data-guide="corroborate-claim">Check a claim</button>
            </>
          )}
          {parts.length > 0 && more && (
            <div className="absolute inset-x-0 bottom-full z-40 flex max-h-[50vh] flex-col gap-2 overflow-auto border-t bg-background px-3 py-2 shadow-md">
              <div className="flex flex-wrap items-center gap-3">
                <button type="button" className="text-muted-foreground underline" onClick={() => setPaste(true)} data-guide="corroborate-paste">Paste a list</button>
                <button type="button" className="text-muted-foreground underline" onClick={() => setClaim({ text: "" })} data-guide="corroborate-claim">Check a claim</button>
                <button type="button" className="text-muted-foreground underline" onClick={() => setSaved(true)} data-guide="corroborate-saved">Save or combine</button>
                <button type="button" className="text-muted-foreground underline" onClick={() => clearSelection(caseId)}>Clear</button>
              </div>
              <ul className="flex flex-wrap gap-1" data-guide="corroborate-parts">
                {parts.map((p) => (
                  <li key={p.id} className="flex items-center gap-1 rounded border bg-muted px-2 py-0.5">
                    <span>{p.label}</span>
                    <span className="text-muted-foreground">· {p.members.length.toLocaleString("en-US")} from {p.screen}</span>
                    {p.skipped.length > 0 && <span className="text-muted-foreground">· {p.skipped.reduce((n, s) => n + s.count, 0)} not readable yet</span>}
                    <button type="button" aria-label={`Remove ${p.label}`} className="px-1 text-muted-foreground hover:text-foreground" onClick={() => removePart(caseId, p.id)}>×</button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
        {dialogs}
      </>
    )
  if (!parts.length)
    return (
      <>
        {/* Nothing selected: the three ways in sit in the page's flow above the bottom bar, as on a phone, so the page
            ends above them instead of under them. A selection in progress floats over the page and follows the
            investigator (below). */}
        <div role="region" aria-label="Corroborate selection" className="flex h-9 shrink-0 items-center justify-end gap-1 border-t bg-background px-3" data-guide="corroborate-tray">
          <Button size="sm" variant="ghost" onClick={() => setPaste(true)} data-guide="corroborate-paste" title="Paste numbers, accounts or plates to corroborate">Paste a list…</Button>
          <Button size="sm" variant="ghost" onClick={() => setSaved(true)} data-guide="corroborate-saved">Saved subsets…</Button>
          <Button size="sm" variant="ghost" onClick={() => setClaim({ text: "" })} data-guide="corroborate-claim" title="Type a sentence someone said and check it against the records">Check a claim…</Button>
        </div>
        {paste && <PasteList caseId={caseId} onClose={() => setPaste(false)} onDone={() => { setPaste(false); ask() }} />}
      {saved && <SavedSubsets caseId={caseId} onClose={() => setSaved(false)} />}
      {claim && <ClaimComposer caseId={caseId} request={claim} onClose={() => setClaim(null)} />}
      </>
    )
  return (
    <>
      <div role="region" aria-label="Corroborate selection" data-guide="corroborate-tray" className="fixed bottom-12 right-3 z-40 flex max-h-[50vh] max-w-[calc(100vw-1.5rem)] flex-col gap-2 overflow-auto rounded-md border bg-background px-3 py-2 text-sm shadow-md sm:max-w-md">
        <div className="flex flex-wrap items-center gap-2">
          <strong>{total.toLocaleString("en-US")} {total === 1 ? "item" : "items"} selected</strong>
          <Button size="sm" onClick={() => ask()} data-guide="corroborate-run">Corroborate</Button>
          <button type="button" className="text-muted-foreground underline" onClick={() => setPaste(true)} data-guide="corroborate-paste">Paste a list</button>
          <button type="button" className="text-muted-foreground underline" onClick={() => setClaim({ text: "" })} data-guide="corroborate-claim">Check a claim</button>
          <button type="button" className="text-muted-foreground underline" onClick={() => setSaved(true)} data-guide="corroborate-saved">Save or combine</button>
          <button type="button" className="text-muted-foreground underline" onClick={() => clearSelection(caseId)}>Clear</button>
        </div>
        <ul className="flex flex-wrap gap-1" data-guide="corroborate-parts">
          {parts.map((p) => (
            <li key={p.id} className="flex items-center gap-1 rounded border bg-muted px-2 py-0.5">
              <span>{p.label}</span>
              <span className="text-muted-foreground">· {p.members.length.toLocaleString("en-US")} from {p.screen}</span>
              {p.skipped.length > 0 && <span className="text-muted-foreground">· {p.skipped.reduce((n, s) => n + s.count, 0)} not readable yet</span>}
              <button type="button" aria-label={`Remove ${p.label}`} className="px-1 text-muted-foreground hover:text-foreground" onClick={() => removePart(caseId, p.id)}>×</button>
            </li>
          ))}
        </ul>
      </div>
      {paste && <PasteList caseId={caseId} onClose={() => setPaste(false)} onDone={() => setPaste(false)} />}
      {saved && <SavedSubsets caseId={caseId} onClose={() => setSaved(false)} />}
      {claim && <ClaimComposer caseId={caseId} request={claim} onClose={() => setClaim(null)} />}
    </>
  )
}
