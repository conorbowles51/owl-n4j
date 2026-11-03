import { Link } from "react-router-dom"
import { useFinancialPresence } from "@/features/phones/financial-presence"

/** 07 section 8: a case with no financial evidence (phones only, so far) says so on the Financial page, with the way
 * to add statements, instead of empty views that read as "0 payments". Nothing is shown once statements exist. */
export function NoFinancialEvidenceNotice({ caseId }: { caseId?: string }) {
  const presence = useFinancialPresence(caseId)
  if (!caseId || !presence.data || presence.data.has_financial_evidence) return null
  return (
    <p role="status" data-testid="no-financial-evidence" className="shrink-0 border-b bg-amber-50 px-4 py-2 text-sm text-amber-950 dark:bg-amber-950 dark:text-amber-50">
      {presence.data.financial_sentence}{" "}
      <Link className="underline" to={`/cases/${encodeURIComponent(caseId)}/evidence`}>Open Evidence</Link>
    </p>
  )
}
