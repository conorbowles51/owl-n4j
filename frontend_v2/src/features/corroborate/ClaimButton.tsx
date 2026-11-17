import { useState } from "react"
import { useSwitch } from "@/lib/ui-switches"
import { ClaimDialog } from "./ClaimDialog"

/** "Corroborate this claim" beside a theory line or a statement line. Behind the switch corroborate-v2. */
export function ClaimButton({ caseId, sentence, source, statementDate }: {
  caseId: string
  sentence: string
  source?: { type: string; id: string; label?: string }
  statementDate?: string
}) {
  const on = useSwitch("corroborate-v2")
  const [open, setOpen] = useState(false)
  if (!on || !sentence.trim()) return null
  return (
    <>
      <button type="button" className="text-xs underline underline-offset-2" onClick={() => setOpen(true)}>Corroborate this claim</button>
      {open && <ClaimDialog caseId={caseId} sentence={sentence} source={source} statementDate={statementDate} onClose={() => setOpen(false)} />}
    </>
  )
}
