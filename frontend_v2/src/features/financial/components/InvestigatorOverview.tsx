import { useInvestigatorPayments } from "../hooks/use-investigator-payments"
import { useMemo, useState } from "react"
import { ArrowRight, Files, BookOpenCheck, WalletCards } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useCaseworkEntries } from "@/features/workspace/hooks/use-casework"
import { useFinancialStore } from "../stores/financial.store"
import { nearbyPayments } from "../lib/investigator-workspace"
import { PaymentTotals } from "./InvestigationTransactionTable"
import {
  InvestigationReadState,
  WorkspaceHeading,
  WorkspaceScope,
} from "./InvestigationWorkspaceParts"
import { useStatementRegister } from "../hooks/use-statement-register"
import { MoneyConnections } from "./InvestigatorFollowMoney"
import { PaymentComparison } from "./PaymentComparison"
import { InvestigatorFindingEditor } from "./InvestigatorFindingEditor"
import { OverviewStatementCoverage } from "./OverviewStatementCoverage"
import { useFinancialAccess } from "../hooks/use-financial-access"

export function InvestigatorOverview({
  caseId,
  active = true,
}: {
  caseId: string
  active?: boolean
}) {
  const data = useInvestigatorPayments(caseId)
  const register = useStatementRegister(caseId, false, [], false, active)
  const findings = useCaseworkEntries(caseId, {
    tag: "financial",
    limit: 4,
    offset: 0,
  })
  const { canEdit } = useFinancialAccess()
  const comparisons = useMemo(() => nearbyPayments(data.rows), [data.rows])
  const [open, setOpen] = useState<{ ids: string[]; title: string } | null>(
    null
  )
  const [finding, setFinding] = useState(false)
  const navigate = useFinancialStore((state) => state.setMainView)
  const files = register.files.data ?? []
  const importedIds = new Set(
    register.imports.data?.files
      .filter(
        (file) => file.current_transactions > 0 || file.periods.length > 0
      )
      .map((file) => file.evidence_file_id)
  )
  const notImported = files.filter((file) => !importedIds.has(file.id))
  const unknownDates = data.rows.filter(
    (row) => row.ordering_date_context === "statement_end_ordering_only"
  ).length
  return (
    <div className="space-y-5 p-5">
      <WorkspaceHeading
        title="Financial investigation"
        description="Start with the records you have, examine the money movements and record what needs explaining."
        action={
          <Button onClick={() => navigate("statements")}>
            Add or review statements
          </Button>
        }
      />
      <WorkspaceScope caseId={caseId} />
      <InvestigationReadState data={data}>
        <PaymentTotals
          rows={data.rows}
          label="Imported payments in the selected accounts and dates"
        />
        <div className="grid gap-5 xl:grid-cols-[minmax(0,2fr)_minmax(260px,1fr)]">
          <div className="min-w-0 space-y-5">
            {data.rows.length ? (
              <MoneyConnections
                rows={data.rows}
                onOpen={(ids, title) => setOpen({ ids, title })}
              />
            ) : (
              <section className="rounded-xl border bg-card p-6 space-y-3">
                <Files className="text-primary" />
                <h3 className="text-lg font-semibold">
                  Start with a statement
                </h3>
                <p className="text-sm text-muted-foreground">
                  Open the file register, upload your PDFs and review their
                  extracted payments against the originals. Confirm each import
                  once, then return here to investigate.
                </p>
                <Button onClick={() => navigate("statements")}>
                  Open statement files
                </Button>
              </section>
            )}
            {!!comparisons.length && (
              <section
                className="finance-panel rounded-xl border p-5 space-y-4"
                data-finance-tone="review"
              >
                <p className="finance-eyebrow text-xs font-medium uppercase tracking-wide">
                  Money in, then money out
                </p>
                <h3 className="text-xl font-semibold">
                  {comparisons.length} times money arrived and the next payment
                  left within a week
                </h3>
                <p className="text-sm text-muted-foreground">
                  For each example, Loupe found money coming into an account,
                  followed by its next recorded payment out within seven days.
                  This is a starting point for review, not evidence of
                  suspicious activity or proof that the incoming money funded
                  the payment.
                </p>
                <div className="flex flex-wrap gap-2">
                  <Button
                    onClick={() =>
                      setOpen({
                        ids: [
                          ...new Set(
                            comparisons.flatMap((pair) => [
                              pair.incoming.key,
                              pair.outgoing.key,
                            ])
                          ),
                        ],
                        title: "Receipts and subsequent payments",
                      })
                    }
                  >
                    View these payments
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => navigate("follow-money")}
                  >
                    Compare incoming and outgoing payments{" "}
                    <ArrowRight size={15} />
                  </Button>
                </div>
              </section>
            )}
            <section
              className="finance-panel rounded-xl border p-5 space-y-3"
              data-finance-tone="work"
            >
              <div className="flex items-center justify-between gap-2">
                <h3 className="font-semibold text-lg">
                  Saved investigation work
                </h3>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => navigate("findings")}
                >
                  Open Findings &amp; Observations
                </Button>
              </div>
              {findings.isPending ? (
                <p role="status">Loading findings…</p>
              ) : findings.isError ? (
                <p role="alert">
                  Saved findings could not be loaded. Open Findings &amp;
                  Observations to try again.
                </p>
              ) : findings.data?.entries.length ? (
                <ul className="divide-y">
                  {findings.data.entries.map((entry) => (
                    <li key={entry.id} className="py-3">
                      <a
                        className="font-medium text-sm hover:underline"
                        href={`/cases/${caseId}/workspace?view=casework&entry=${entry.id}`}
                      >
                        {entry.title || "Untitled note"}
                      </a>
                      <p className="text-xs text-muted-foreground">
                        {entry.author_name ||
                          entry.author_email ||
                          "Author not recorded"}
                        {entry.updated_at
                          ? ` · ${new Date(entry.updated_at).toLocaleDateString()}`
                          : ""}
                      </p>
                    </li>
                  ))}
                </ul>
              ) : (
                <>
                  <p className="text-sm text-muted-foreground">
                    No findings saved yet. Write a question to follow up, or
                    select payments and record what you noticed with the
                    evidence attached.
                  </p>
                  {canEdit && (
                    <Button variant="outline" onClick={() => setFinding(true)}>
                      Create observation
                    </Button>
                  )}
                </>
              )}
            </section>
          </div>
          <aside className="space-y-4">
            <section
              className="finance-panel rounded-xl border p-5 space-y-4"
              data-finance-tone="review"
            >
              <div className="flex gap-2 items-center">
                <BookOpenCheck size={19} className="finance-icon" />
                <h3 className="font-semibold">Your statements</h3>
              </div>
              {register.files.isError || register.imports.isError ? (
                <p role="alert" className="text-sm">
                  Statement status could not be loaded. Open the file register
                  to try again.
                </p>
              ) : register.files.isPending || register.imports.isPending ? (
                <p role="status">Checking statement files…</p>
              ) : (
                <>
                  <dl className="space-y-3 text-sm">
                    <div className="flex justify-between">
                      <dt>Files added for financial review</dt>
                      <dd className="font-semibold">{files.length}</dd>
                    </div>
                    <div className="flex justify-between">
                      <dt>Files with saved statements</dt>
                      <dd className="font-semibold">{importedIds.size}</dd>
                    </div>
                    <div className="flex justify-between">
                      <dt>Files with no saved statements yet</dt>
                      <dd className="font-semibold">{notImported.length}</dd>
                    </div>
                    <div className="flex justify-between gap-3">
                      <dt>Statements ready to save together</dt>
                      <dd className="font-semibold">
                        {register.imports.data?.files.reduce(
                          (sum, file) => sum + file.available_periods,
                          0
                        ) ?? 0}
                      </dd>
                    </div>
                    <div className="flex justify-between gap-3">
                      <dt>Statements needing a check</dt>
                      <dd className="font-semibold">
                        {register.imports.data?.files.reduce(
                          (sum, file) => sum + file.periods_with_checks,
                          0
                        ) ?? 0}
                      </dd>
                    </div>
                  </dl>
                  {register.imports.data?.truncated && (
                    <p role="alert" className="text-sm">
                      Import status is incomplete. Check each file for its full
                      record.
                    </p>
                  )}
                  <p className="text-xs text-muted-foreground">
                    These file counts cover the whole case. Saved statements are
                    available for investigation, including statements with no
                    transactions. Files not yet saved may be waiting for review,
                    still being read, or duplicate copies. One file can contain
                    several statements.
                  </p>
                </>
              )}
              {unknownDates > 0 && (
                <p className="text-sm">
                  {unknownDates} payments have only a statement end date. Check
                  their original records before comparing timing.
                </p>
              )}
              <Button
                className="w-full"
                variant="outline"
                onClick={() => navigate("statements")}
              >
                See what needs saving
              </Button>
            </section>
            <OverviewStatementCoverage caseId={caseId} active={active} />
            <section
              className="finance-panel rounded-xl border p-5 space-y-3"
              data-finance-tone="info"
            >
              <WalletCards size={20} className="finance-icon" />
              <h3 className="font-semibold">
                {new Set(data.rows.map((row) => row.account_id)).size} accounts
                with payments in this scope
              </h3>
              <p className="text-sm text-muted-foreground">
                Check account holders, statement periods and missing coverage in
                Statements & accounts.
              </p>
              <Button variant="outline" onClick={() => navigate("statements")}>
                Review accounts and coverage
              </Button>
            </section>
            <section
              className="finance-panel rounded-xl border p-5 space-y-3"
              data-finance-tone="info"
            >
              <h3 className="font-semibold">Explore activity over time</h3>
              <p className="text-sm text-muted-foreground">
                Compare periods, open the entries behind a change and save your
                explanation.
              </p>
              <Button variant="outline" onClick={() => navigate("trends")}>
                Open Trends
              </Button>
            </section>
          </aside>
        </div>
      </InvestigationReadState>
      {open && (
        <PaymentComparison
          caseId={caseId}
          ids={open.ids}
          title={open.title}
          onClose={() => setOpen(null)}
        />
      )}
      {finding && (
        <InvestigatorFindingEditor
          caseId={caseId}
          onClose={() => setFinding(false)}
        />
      )}
    </div>
  )
}
