import { useEffect, useState } from "react"
import { useParams } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { useMediaQuery } from "@/hooks/use-media-query"
import { clearSelection, removePart, selectionCount, useSelection } from "./selection-store"
import { QuestionMenu } from "./QuestionMenu"
import { PasteList } from "./PasteList"
import { SavedSubsets } from "./SavedSubsets"
import { ClaimComposer } from "./ClaimComposer"
import { CLAIM_EVENT, type ClaimComposerRequest } from "./claim-composer"

/**
 * The selection tray (lx-corroselect B): every part of the case-wide selection as a removable chip with its count and
 * the screen it came from, the whole count, and the way to the question menu. It follows the investigator.
 * Below md it is a one-line strip in the page's own flow, above the bottom bar: the page ends above it instead of under
 * it (a floating tray covered the agent's message box at 390 px), and "More" opens the rest over the page.
 */
export function CorroborateTray() {
  const { id: caseId } = useParams()
  const parts = useSelection(caseId)
  const [menu, setMenu] = useState(false)
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
  const dialogs = (
    <>
      {paste && <PasteList caseId={caseId} onClose={() => setPaste(false)} onDone={() => { setPaste(false); if (!parts.length) setMenu(true) }} />}
      {menu && <QuestionMenu caseId={caseId} onClose={() => setMenu(false)} />}
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
              <Button size="sm" onClick={() => setMenu(true)} data-guide="corroborate-run">Corroborate</Button>
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
        <div className="fixed bottom-12 right-3 z-40" data-guide="corroborate-tray">
          <Button size="sm" variant="outline" onClick={() => setPaste(true)} data-guide="corroborate-paste" title="Paste numbers, accounts or plates to corroborate">Paste a list…</Button>
          <Button size="sm" variant="outline" className="ml-1" onClick={() => setSaved(true)} data-guide="corroborate-saved">Saved subsets…</Button>
          <Button size="sm" variant="outline" className="ml-1" onClick={() => setClaim({ text: "" })} data-guide="corroborate-claim" title="Type a sentence someone said and check it against the records">Check a claim…</Button>
        </div>
        {paste && <PasteList caseId={caseId} onClose={() => setPaste(false)} onDone={() => { setPaste(false); setMenu(true) }} />}
        {menu && <QuestionMenu caseId={caseId} onClose={() => setMenu(false)} />}
      {saved && <SavedSubsets caseId={caseId} onClose={() => setSaved(false)} />}
      {claim && <ClaimComposer caseId={caseId} request={claim} onClose={() => setClaim(null)} />}
      </>
    )
  return (
    <>
      <div role="region" aria-label="Corroborate selection" data-guide="corroborate-tray" className="fixed bottom-12 right-3 z-40 flex max-h-[50vh] max-w-[calc(100vw-1.5rem)] flex-col gap-2 overflow-auto rounded-md border bg-background px-3 py-2 text-sm shadow-md sm:max-w-md">
        <div className="flex flex-wrap items-center gap-2">
          <strong>{total.toLocaleString("en-US")} {total === 1 ? "item" : "items"} selected</strong>
          <Button size="sm" onClick={() => setMenu(true)} data-guide="corroborate-run">Corroborate</Button>
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
      {menu && <QuestionMenu caseId={caseId} onClose={() => setMenu(false)} />}
      {saved && <SavedSubsets caseId={caseId} onClose={() => setSaved(false)} />}
      {claim && <ClaimComposer caseId={caseId} request={claim} onClose={() => setClaim(null)} />}
    </>
  )
}
