import { useState } from "react"
import { useParams } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { clearSelection, removePart, selectionCount, useSelection } from "./selection-store"
import { QuestionMenu } from "./QuestionMenu"
import { PasteList } from "./PasteList"

/**
 * The selection tray (lx-corroselect B): every part of the case-wide selection as a removable chip with its count and
 * the screen it came from, the whole count, and the way to the question menu. It follows the investigator.
 */
export function CorroborateTray() {
  const { id: caseId } = useParams()
  const parts = useSelection(caseId)
  const [menu, setMenu] = useState(false)
  const [paste, setPaste] = useState(false)
  if (!caseId) return null
  const total = selectionCount(parts)
  if (!parts.length)
    return (
      <>
        <div className="fixed bottom-3 right-3 z-40">
          <Button size="sm" variant="outline" onClick={() => setPaste(true)} title="Paste numbers, accounts or plates to corroborate">Paste a list…</Button>
        </div>
        {paste && <PasteList caseId={caseId} onClose={() => setPaste(false)} onDone={() => { setPaste(false); setMenu(true) }} />}
        {menu && <QuestionMenu caseId={caseId} onClose={() => setMenu(false)} />}
      </>
    )
  return (
    <>
      <div role="region" aria-label="Corroborate selection" className="fixed bottom-3 right-3 z-40 flex max-h-[50vh] max-w-[calc(100vw-1.5rem)] flex-col gap-2 overflow-auto rounded-md border bg-background px-3 py-2 text-sm shadow-md sm:max-w-md">
        <div className="flex flex-wrap items-center gap-2">
          <strong>{total.toLocaleString("en-US")} {total === 1 ? "item" : "items"} selected</strong>
          <Button size="sm" onClick={() => setMenu(true)}>Corroborate</Button>
          <button type="button" className="text-muted-foreground underline" onClick={() => setPaste(true)}>Paste a list</button>
          <button type="button" className="text-muted-foreground underline" onClick={() => clearSelection(caseId)}>Clear</button>
        </div>
        <ul className="flex flex-wrap gap-1">
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
    </>
  )
}
