import { SourceCustodyPanel } from "./SourceCustodyPanel"
import { useState } from "react"
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
  finalization_id: z.string().uuid(),
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
  recorded_digest_matches: z.literal(true),
  file_bytes_verified: z.literal(false),
  limitation: z.string(),
  reviewed_controls: retainedControls.nullable().optional(),
})
export function StatementSourceButton({
  caseId,
  periodId,
  sourceDocumentId,
}: {
  caseId: string
  periodId: string
  sourceDocumentId: string
}) {
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
        data.source_document_id !== sourceDocumentId
      )
        throw new Error("The source does not match this statement.")
      return data
    },
  })
  return (
    <>
      <Button variant="outline" onClick={() => setOpened(true)}>
        Inspect statement source
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
              {query.data.reviewed_controls && (
                <section
                  aria-label="Retained statement controls"
                  className="space-y-3"
                >
                  <p className="text-sm text-muted-foreground">
                    Saved when these rows were finalized.
                  </p>
                  <p>
                    {query.data.reviewed_controls.balance_convention ===
                    "liability_owed"
                      ? "Printed amounts owed were converted to negative ledger balances. Original printed values are preserved below."
                      : "Printed balances represent money held in the account."}
                  </p>
                  <details className="text-sm">
                    <summary>Review reason and scope</summary>
                    <p>{query.data.reviewed_controls.reason}</p>
                    <p>{query.data.reviewed_controls.scope}</p>
                  </details>
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
                        <p>Original text: {control.original_text}</p>
                        <TransactionSourceHighlight
                          sourceDocumentId={query.data.evidence_file_id}
                          locatorPayload={control.locator}
                        />
                      </div>
                    ))}
                </section>
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
        />
      )}
    </>
  )
}
