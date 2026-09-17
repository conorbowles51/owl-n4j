import { useSearchParams } from "react-router-dom"
import { FinancialBatchPanel } from "./FinancialBatchPanel"
import { Button } from "@/components/ui/button"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import { useStatementWorkspace } from "../stores/statement-workspace"
import { StatementFilesPanel } from "./StatementFilesPanel"
import type { ReactNode } from "react"

export function StatementRegister({
  caseId,
  children,
}: {
  caseId: string
  children: ReactNode
}) {
  const [params] = useSearchParams()
  const owner = useAuthStore(
    (state) => state.user?.id || state.user?.username || "anonymous"
  )
  const scope = `${owner}:${caseId}`
  const review = useStatementWorkspace((state) => state.selections[scope])
  const open = !!review?.open
  if (params.get("batch")) return <FinancialBatchPanel caseId={caseId} />
  return (
    <div className="space-y-4">
      {!open && <FinancialBatchPanel caseId={caseId} />}
      <div hidden={open}>
        <StatementFilesPanel caseId={caseId} register />
      </div>
      <div hidden={!open} className="space-y-3">
        <Button
          variant="outline"
          onClick={() => useStatementWorkspace.getState().setOpen(scope, false)}
        >
          Back to all statement files
        </Button>
        {children}
      </div>
      {!open && review?.fileId && (
        <Button
          variant="outline"
          onClick={() => useStatementWorkspace.getState().setOpen(scope, true)}
        >
          Continue last statement review
        </Button>
      )}
    </div>
  )
}
