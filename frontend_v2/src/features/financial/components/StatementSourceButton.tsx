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
const source = z.object({
  case_id: z.string(),
  period_id: z.string(),
  source_document_id: z.string(),
  evidence_file_id: z.string().uuid(),
  filename: z.string(),
  recorded_digest_matches: z.literal(true),
  file_bytes_verified: z.literal(false),
  limitation: z.string(),
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
    [viewFile, setViewFile] = useState(false)
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
        <DialogContent>
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
              <p>{query.data.filename}</p>
              <p>{query.data.limitation}</p>
              <p>
                Recorded file digests agree. Opening this citation does not
                freshly verify the file bytes or its financial readings.
              </p>
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
