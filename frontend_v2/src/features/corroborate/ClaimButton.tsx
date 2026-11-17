import { useSwitch } from "@/lib/ui-switches"
import { openClaimComposer } from "./claim-composer"

/**
 * "Corroborate this claim" beside a theory line or a statement line (lx-corrorest A). It opens lx-corrostatement's claim
 * composer with the line as the sentence: the chips are read there, shown as not confirmed, and nothing runs until the
 * person confirms. Behind the switch corroborate-v2.
 */
export function ClaimButton({ sentence, source, statementDate }: {
  caseId?: string
  sentence: string
  source?: { type: string; id: string; label?: string }
  statementDate?: string
}) {
  const on = useSwitch("corroborate-v2")
  if (!on || !sentence.trim()) return null
  return (
    <button type="button" className="text-xs underline underline-offset-2"
      onClick={() => openClaimComposer({ text: sentence, ...(statementDate ? { statementDate } : {}), ...(source ? { source } : {}) })}>
      Corroborate this claim
    </button>
  )
}
