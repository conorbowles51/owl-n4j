import { useMemo } from "react"
import { useInvestigatorPayments } from "../hooks/use-investigator-payments"
import { useStatementRegister } from "../hooks/use-statement-register"
import {
  InvestigationReadState,
  WorkspaceHeading,
  WorkspaceScope,
} from "./InvestigationWorkspaceParts"
import { TrendComparisonWorkspace } from "./TrendComparisonWorkspace"
import { useFinancialStore } from "../stores/financial.store"
import {
  financialDraftKey,
  useFinancialDraftStore,
} from "../stores/financial-drafts"
import { Button } from "@/components/ui/button"
import { paymentTableDraftName } from "../lib/payment-table-draft"
import { AccountHistory } from "./AccountHistory"

export function InvestigatorTrends({ caseId, active = true }: { caseId: string; active?: boolean }) {
  const data = useInvestigatorPayments(caseId)
  const register = useStatementRegister(caseId, false, [], false, active)
  const coverage = useMemo(
    () => ({
      available: !!register.imports.data && !register.imports.isError,
      truncated: register.imports.data?.truncated ?? false,
      periods:
        register.imports.data?.files.flatMap((file) =>
          file.periods.map((period) => ({
            ...period,
            incomplete:
              file.incomplete_count > 0 ||
              file.receipt_review_count > 0 ||
              file.wire_review_count > 0,
          }))
        ) ?? [],
    }),
    [register.imports.data, register.imports.isError]
  )
  const openCharts = () => {
    const key = financialDraftKey(
      caseId,
      paymentTableDraftName(data.params, true)
    )
    const drafts = useFinancialDraftStore.getState()
    drafts.put(key, {
      ...((drafts.drafts[key] as object) || {}),
      chartsOpen: true,
    })
    useFinancialStore.getState().setMainView("transactions")
  }
  return (
    <div className="space-y-5 p-5">
      <WorkspaceHeading
        title="Trends"
        description="Compare periods, see what drove a change, and inspect the payments behind each observation."
        action={
          <Button variant="outline" onClick={openCharts}>
            Charts in Transactions
          </Button>
        }
      />
      <WorkspaceScope caseId={caseId} />
      <AccountHistory caseId={caseId} />
      <InvestigationReadState data={data}>
        <TrendComparisonWorkspace
          caseId={caseId}
          rows={data.rows}
          coverage={coverage}
          loadedStart={data.params.startDate}
          loadedEnd={data.params.endDate}
          onCoverageRetry={() => void register.imports.refetch()}
        />
      </InvestigationReadState>
    </div>
  )
}
