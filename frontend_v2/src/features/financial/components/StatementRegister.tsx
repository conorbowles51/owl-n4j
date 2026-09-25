import { useSearchParams } from "react-router-dom"
import { FinancialBatchPanel } from "./FinancialBatchPanel"
import { Button } from "@/components/ui/button"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import { useStatementWorkspace } from "../stores/statement-workspace"
import { StatementFilesPanel } from "./StatementFilesPanel"
import { useEffect, useRef, type ReactNode } from "react"

export function StatementRegister({
  caseId,
  children,
  mode = "files",
  onBackToFiles,
  active = true,
}: {
  caseId: string
  children: ReactNode
  mode?: "files" | "batches" | "remove"
  onBackToFiles?: () => void
  active?: boolean
}) {
  const [params] = useSearchParams()
  const owner = useAuthStore(
    (state) => state.user?.id || state.user?.username || "anonymous"
  )
  const scope = `${owner}:${caseId}`
  const review = useStatementWorkspace((state) => state.selections[scope])
  const open = !!review?.open
  const batches = mode === "batches" || !!params.get("batch")
  const reviewPanel = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open || batches || mode === "remove") return
    reviewPanel.current?.focus({ preventScroll: true })
    reviewPanel.current?.scrollIntoView({ block: "start" })
  }, [open, batches, mode, review?.fileId])
  return (
    <div className="space-y-4">
      {batches && <FinancialBatchPanel caseId={caseId} />}
      <div hidden={batches || (open && mode !== "remove")}>
        <StatementFilesPanel
          caseId={caseId}
          register
          active={active && !batches && (!open || mode === "remove")}
          removalMode={mode === "remove"}
          onFinishRemoval={onBackToFiles}
        />
      </div>
      <div
        ref={reviewPanel}
        tabIndex={-1}
        aria-label="Selected statement review"
        hidden={batches || !open || mode === "remove"}
        className="space-y-3 scroll-mt-24 focus:outline-none"
      >
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
