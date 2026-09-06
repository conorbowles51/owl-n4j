import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { z } from "zod"
import { fetchAPI } from "@/lib/api-client"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog"
import { DocumentViewer } from "@/components/ui/document-viewer"
import { Button } from "@/components/ui/button"
import { evidenceAPI } from "@/features/evidence/api"
import { readLocator } from "../lib/locator"
import { TransactionSourceHighlight } from "./TransactionSourceHighlight"

const citationSchema = z.object({
  case_id: z.string(),
  transaction_id: z.string(),
  ref_id: z.string(),
  source_document_id: z.string(),
  evidence_file_id: z.string().uuid(),
  filename: z.string(),
  sha256_at_ingestion: z.string().regex(/^[a-f0-9]{64}$/),
  recorded_digest_matches: z.literal(true),
  file_bytes_verified: z.literal(false),
  locator_state: z.enum(["stored", "missing", "invalid"]),
  locator: z.unknown(),
  ledger_status: z.string(),
  superseded_by_id: z.string().nullable(),
  limitation: z.string(),
})

export function LedgerSourceDialog({
  caseId,
  transactionId,
  onClose,
}: {
  caseId: string
  transactionId: string
  onClose: () => void
}) {
  const [viewFile, setViewFile] = useState(false)
  const source = useQuery({
    queryKey: ["ledger-source", caseId, transactionId],
    retry: false,
    queryFn: async () => {
      const data = citationSchema.parse(
        await fetchAPI(
          `/api/financial/ledger/${encodeURIComponent(transactionId)}/source?${new URLSearchParams({ case_id: caseId })}`
        )
      )
      if (
        data.case_id !== caseId ||
        data.transaction_id !== transactionId ||
        (data.locator_state === "stored"
          ? !readLocator(data.locator).ok
          : data.locator !== null)
      )
        throw new Error(
          "Source citation is inconsistent. Reload the ledger before opening it."
        )
      return data
    },
  })
  const data = source.data
  const location = data ? readLocator(data.locator) : null
  const page =
    location?.ok && "page" in location.locator
      ? (location.locator.page ?? undefined)
      : undefined
  return (
    <>
      <Dialog
        open={!viewFile || source.isError}
        onOpenChange={(open) => !open && onClose()}
      >
        <DialogContent className="sm:max-w-3xl max-h-[90vh] overflow-auto">
          <DialogHeader>
            <DialogTitle>Ledger source</DialogTitle>
            <DialogDescription>
              Inspect the source cited by this reading. Opening it does not
              change the ledger.
            </DialogDescription>
          </DialogHeader>
          {source.isPending && <p>Loading source citation…</p>}
          {source.isError && <p role="alert">{source.error.message}</p>}
          {data && !source.isError && (
            <>
              <p className="font-medium">
                {data.ref_id} · {data.filename}
              </p>
              {data.ledger_status === "superseded" && (
                <p>This is an original reading that has been replaced.</p>
              )}
              {data.locator_state === "missing" && (
                <p>
                  No location was stored for this row. You can open the source
                  file.
                </p>
              )}
              {data.locator_state === "invalid" && (
                <p>
                  The stored location could not be read. You can open the source
                  file without a highlight.
                </p>
              )}
              {data.locator_state === "stored" && (
                <TransactionSourceHighlight
                  locatorPayload={data.locator}
                  sourceDocumentId={
                    data.filename.toLowerCase().endsWith(".pdf")
                      ? data.evidence_file_id
                      : undefined
                  }
                  valueLabel={data.ref_id}
                />
              )}
              <p className="text-sm text-muted-foreground">{data.limitation}</p>
              <Button onClick={() => setViewFile(true)}>
                Open source file
              </Button>
            </>
          )}
        </DialogContent>
      </Dialog>
      {data && !source.isError && (
        <DocumentViewer
          open={viewFile}
          onOpenChange={setViewFile}
          documentUrl={evidenceAPI.getFileUrl(data.evidence_file_id)}
          documentName={data.filename}
          initialPage={page}
          navigationKey={`${caseId}:${transactionId}`}
        />
      )}
    </>
  )
}
