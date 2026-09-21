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
  mode = "files",
  onBackToFiles,
}: {
  caseId: string
  children: ReactNode
  mode?: "files" | "batches" | "remove"
  onBackToFiles?: () => void
}) {
  const [params] = useSearchParams()
  const owner = useAuthStore(
    (state) => state.user?.id || state.user?.username || "anonymous"
  )
  const scope = `${owner}:${caseId}`
  const review = useStatementWorkspace((state) => state.selections[scope])
  const open = !!review?.open
  const batches = mode === "batches" || !!params.get("batch")
  return (
    <div className="space-y-4">
      {batches && <FinancialBatchPanel caseId={caseId} />}
      <div hidden={batches || (open && mode !== "remove")}>
        <StatementFilesPanel
          caseId={caseId}
          register
          removalMode={mode === "remove"}
          onFinishRemoval={onBackToFiles}
        />
      </div>
      <div hidden={batches || !open || mode === "remove"} className="space-y-3">
        {children}
      </div>
      {!batches && !open && mode === "files" && review && (
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
