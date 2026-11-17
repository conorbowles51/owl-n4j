import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { setCurrentQuery } from "@/features/relations/api"
import { corroborateAPI, type Claim, type ClaimChip, type ClaimField } from "./api"

const FIELDS: { key: ClaimField; label: string }[] = [
  { key: "who", label: "Who" },
  { key: "when", label: "When" },
  { key: "where", label: "Where" },
  { key: "what", label: "What" },
]

/**
 * "Corroborate this claim" (lx-corrorest A). The line is read into who, when, where and what by the claim parser
 * (lx-corrostatement). Each chip says it was read by Loupe and not confirmed, shows the words it came from, and can be
 * edited. A chip the parser could not fill says so. Nothing runs until the person confirms the chips.
 */
export function ClaimDialog({ caseId, sentence, source, statementDate, onClose }: {
  caseId: string
  sentence: string
  source?: { type: string; id: string; label?: string }
  statementDate?: string
  onClose: () => void
}) {
  const navigate = useNavigate()
  const [claim, setClaim] = useState<Claim | null>(null)
  const [chips, setChips] = useState<Record<ClaimField, ClaimChip> | null>(null)
  const [busy, setBusy] = useState<string | null>("Reading the line…")
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let live = true
    corroborateAPI.parseClaim(caseId, { text: sentence, ...(statementDate ? { statement_date: statementDate } : {}), ...(source ? { source } : {}) })
      .then((r) => { if (live) { setClaim(r.claim); setChips(r.claim.chips) } })
      .catch((e) => { if (live) setError(e instanceof Error ? e.message : "The line could not be read. Nothing was saved.") })
      .finally(() => { if (live) setBusy(null) })
    return () => { live = false }
  }, [caseId, sentence, statementDate, source])

  const edit = (key: ClaimField, value: string) => {
    if (!chips) return
    // An edited chip is the person's own reading, no longer Loupe's.
    setChips({ ...chips, [key]: { ...chips[key], value: value || null, read_by: "Edited by you" } })
  }
  const run = async () => {
    if (!claim || !chips) return
    setBusy("Confirming and starting…")
    setError(null)
    try {
      const confirmed = await corroborateAPI.confirmClaim(caseId, claim.id, chips)
      const made = await corroborateAPI.run(caseId, {
        members: [{ type: "claim", id: confirmed.claim.id, label: sentence.slice(0, 120) }],
        surface: "corroborate",
        question: { kind: "statement", text: sentence, chips: { claim_id: confirmed.claim.id } },
      })
      setCurrentQuery(caseId, { id: made.group.id, count: made.group.member_count })
      onClose()
      navigate(`/cases/${caseId}/relations/${made.group.id}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Corroborate could not start. Nothing was run.")
      setBusy(null)
    }
  }
  return (
    <Dialog open onOpenChange={(o) => !o && !busy && onClose()}>
      <DialogContent className="max-h-[90vh] max-w-xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Corroborate this claim</DialogTitle>
          <DialogDescription>Loupe read the line into the parts below. Check them and change any that are wrong. Nothing runs until you confirm.</DialogDescription>
        </DialogHeader>
        <blockquote className="rounded border-l-2 px-2 py-1 text-sm italic">{sentence}</blockquote>
        {busy && !chips && <p role="status" className="text-sm">{busy}</p>}
        {chips && (
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {FIELDS.map(({ key, label }) => (
              <label key={key} className="flex flex-col text-xs text-muted-foreground">
                {label}
                <input className="rounded border bg-card px-2 py-1 text-sm text-foreground" value={chips[key].value ?? ""} placeholder={`${label.toLowerCase()}: not stated`}
                  onChange={(e) => edit(key, e.target.value)} />
                <span>{chips[key].value ? chips[key].read_by : `${label.toLowerCase()}: not stated, so it is not guessed`}{chips[key].words ? ` · from "${chips[key].words}"` : ""}</span>
              </label>
            ))}
          </div>
        )}
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        <DialogFooter className="gap-2">
          <Button disabled={!!busy || !claim} onClick={() => void run()}>{busy && chips ? busy : "Confirm and corroborate"}</Button>
          <Button variant="ghost" disabled={!!busy} onClick={onClose}>Cancel</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
