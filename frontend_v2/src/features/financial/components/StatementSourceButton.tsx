import { ImportedStatementDetails } from "./ImportedStatementDetails"
import { useFinancialAccess } from "../hooks/use-financial-access"
import { SourceCustodyPanel } from "./SourceCustodyPanel"
import { useState } from "react"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import { useStatementWorkspace } from "../stores/statement-workspace"
import { useQuery } from "@tanstack/react-query"
import { z } from "zod"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog"
import { DocumentViewer } from "@/components/ui/document-viewer"
import { fetchAPI } from "@/lib/api-client"
import { evidenceAPI } from "@/features/evidence/api"
import { assertCandidateScope, candidateUrl } from "../lib/candidate-contract"
import { TransactionSourceHighlight } from "./TransactionSourceHighlight"
import { correctionMoney } from "../lib/correction-contract"
const retainedControls = z.object({
  account_closure: z
    .object({
      date: z.string(),
      original_text: z.string(),
      locator: z.unknown(),
    })
    .nullable()
    .optional(),
  finalization_id: z.string().uuid().nullable(),
  import_source_document_id: z.string().uuid().optional(),
  currency: z.string().regex(/^[A-Z]{3}$/),
  balance_convention: z.enum(["asset_balance", "liability_owed"]),
  reason: z.string(),
  scope: z.string(),
  controls: z
    .array(
      z.object({
        role: z.enum([
          "start",
          "end",
          "opening",
          "closing",
          "credits_total",
          "debits_total",
        ]),
        original_text: z.string(),
        reviewed_value: z.string(),
        locator: z.unknown(),
      })
    )
    .max(6),
})
const source = z.object({
  case_id: z.string(),
  period_id: z.string(),
  source_document_id: z.string(),
  evidence_file_id: z.string().uuid(),
  filename: z.string(),
  statement_id: z
    .string()
    .regex(/^[a-f0-9]{64}$/)
    .nullish(),
  recorded_digest_matches: z.literal(true),
  file_bytes_verified: z.literal(false),
  limitation: z.string(),
  reviewed_controls: retainedControls.nullable().optional(),
  can_edit_import_details: z.boolean().default(false),
})
export function StatementSourceButton({
  caseId,
  periodId,
  sourceDocumentId,
  onReviewStatement,
  label = "Inspect statement source",
}: {
  caseId: string
  periodId: string
  sourceDocumentId: string
  onReviewStatement?: (fileId: string) => void
  label?: string
}) {
  const { canEdit } = useFinancialAccess()
  const [opened, setOpened] = useState(false),
    [viewFile, setViewFile] = useState(false),
    [controlRole, setControlRole] = useState<string | null>(null)
  const query = useQuery({
    queryKey: ["statement-source", caseId, periodId, sourceDocumentId],
    enabled: opened,
    retry: false,
    queryFn: async () => {
      const data = source.parse(
        await fetchAPI<unknown>(
          candidateUrl(
            `statement-periods/${encodeURIComponent(periodId)}/source`,
            caseId
          )
        )
      )
      assertCandidateScope(data, caseId)
      if (
        data.period_id !== periodId ||
        data.source_document_id !== sourceDocumentId ||
        (data.reviewed_controls?.import_source_document_id &&
          data.reviewed_controls.import_source_document_id !== sourceDocumentId)
      )
        throw new Error("The source does not match this statement.")
      return data
    },
  })
  return (
    <>
      <Button variant="outline" onClick={() => setOpened(true)}>
        {label}
      </Button>
      <Dialog
        open={opened && (!viewFile || query.isError)}
        onOpenChange={setOpened}
      >
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-4xl">
          <DialogHeader>
            <DialogTitle>Statement source</DialogTitle>
            <DialogDescription>
              Inspect the registered document for this statement period.
            </DialogDescription>
          </DialogHeader>
          {query.isPending ? (
            <p role="status">Loading statement citation…</p>
          ) : query.isError ? (
            <p role="alert">Source unavailable. {query.error.message}</p>
          ) : (
            <>
              <SourceCustodyPanel
                caseId={caseId}
                fileId={query.data.evidence_file_id}
              />
              <p>{query.data.filename}</p>
              <details className="text-sm text-muted-foreground">
                <summary>Source verification details</summary>
                <p>{query.data.limitation}</p>
                <p>
                  Recorded file digests agree. Opening this citation does not
                  freshly verify the file bytes or its financial readings.
                </p>
              </details>
              {canEdit && query.data.can_edit_import_details && (
                <ImportedStatementDetails
                  caseId={caseId}
                  sourceId={sourceDocumentId}
                  withSource
                />
              )}
              {query.data.reviewed_controls && (
                <section
                  aria-label="Retained statement controls"
                  className="space-y-3"
                >
                  <p className="text-sm text-muted-foreground">
                    Saved with this statement import. Select an amount to see
                    where it appears in the PDF.
                  </p>
                  <p>
                    {query.data.reviewed_controls.balance_convention ===
                    "liability_owed"
                      ? "These are amounts owed on the card. Payments reduce them; charges increase them."
                      : "Printed balances represent money held in the account."}
                  </p>
                  <details className="text-sm">
                    <summary>Review reason and scope</summary>
                    <p>{query.data.reviewed_controls.reason}</p>
                    <p>{query.data.reviewed_controls.scope}</p>
                  </details>
                  {query.data.reviewed_controls.account_closure && (
                    <div className="space-y-2">
                      <p>
                        Account closed on{" "}
                        {query.data.reviewed_controls.account_closure.date}, as
                        recorded in this statement. A closure notice does not
                        establish a final account balance.
                      </p>
                      <Button
                        variant="outline"
                        onClick={() => setControlRole("account_closure")}
                      >
                        Inspect account closure notice
                      </Button>
                      {controlRole === "account_closure" && (
                        <>
                          <p>
                            Original text:{" "}
                            {
                              query.data.reviewed_controls.account_closure
                                .original_text
                            }
                          </p>
                          <TransactionSourceHighlight
                            sourceDocumentId={query.data.evidence_file_id}
                            locatorPayload={
                              query.data.reviewed_controls.account_closure
                                .locator
                            }
                          />
                        </>
                      )}
                    </div>
                  )}
                  <div className="grid gap-2 sm:grid-cols-2">
                    {query.data.reviewed_controls.controls.map((control) => (
                      <Button
                        key={control.role}
                        variant="outline"
                        className="h-auto whitespace-normal text-left"
                        onClick={() => setControlRole(control.role)}
                      >
                        Inspect{" "}
                        {control.role === "credits_total"
                          ? "total money in"
                          : control.role === "debits_total"
                            ? "total money out"
                            : control.role}
                        :{" "}
                        {control.role === "opening" ||
                        control.role === "closing" ||
                        control.role.endsWith("_total")
                          ? correctionMoney(
                              control.reviewed_value,
                              query.data.reviewed_controls!.currency
                            )
                          : control.reviewed_value}
                      </Button>
                    ))}
                  </div>
                  {query.data.reviewed_controls.controls
                    .filter((control) => control.role === controlRole)
                    .map((control) => (
                      <div key={control.role} className="space-y-2">
                        <p>
                          {control.original_text
                            ? `Original text: ${control.original_text}`
                            : "Balance entered by a reviewer from this PDF page."}
                        </p>
                        <TransactionSourceHighlight
                          sourceDocumentId={query.data.evidence_file_id}
                          locatorPayload={control.locator}
                        />
                      </div>
                    ))}
                </section>
              )}
              {onReviewStatement && (
                <div className="rounded border p-3 space-y-2">
                  <p className="text-sm">
                    If transactions were missed or the extraction is wrong, open
                    the statement review and use Read the statement again.
                    Confirm replacement only after checking the new reading.
                  </p>
                  <Button
                    variant="outline"
                    onClick={() => {
                      setOpened(false)
                      const user = useAuthStore.getState().user
                      const owner = user?.id || user?.username || "anonymous"
                      useStatementWorkspace
                        .getState()
                        .setReviewChoice(
                          `${owner}:${caseId}:${query.data.evidence_file_id}`,
                          {
                            statementId: query.data.statement_id || "",
                            currency: "",
                          }
                        )
                      onReviewStatement(query.data.evidence_file_id)
                    }}
                  >
                    Review or reread statement
                  </Button>
                </div>
              )}
              <Button onClick={() => setViewFile(true)}>
                Open statement file
              </Button>
            </>
          )}
        </DialogContent>
      </Dialog>
      {query.data && !query.isError && (
        <DocumentViewer
          open={opened && viewFile}
          onOpenChange={setViewFile}
          documentUrl={evidenceAPI.getFileUrl(query.data.evidence_file_id)}
          documentName={query.data.filename}
          navigationKey={`${caseId}:${periodId}`}
          caseId={caseId}
          evidenceId={query.data.evidence_file_id}
        />
      )}
    </>
  )
}
