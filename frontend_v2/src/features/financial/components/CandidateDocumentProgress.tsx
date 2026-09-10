import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { z } from "zod"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import { candidateUrl, assertCandidateScope } from "../lib/candidate-contract"
const count = z.number().int().nonnegative()
const counts = z.object({ pending: count, resolved: count, rejected: count })
const schema = z.object({
  case_id: z.string(),
  evidence_file_id: z.string(),
  filename: z.string(),
  counts,
  unlocated_readings: count,
  applied: z.literal(false),
  limitation: z.string(),
  pages: z
    .array(
      z.object({
        page_number: z.number().int().positive(),
        prepared: z.boolean(),
        counts,
        batches: z.array(
          counts.extend({
            mapping_id: z.string(),
            next_pending_candidate_id: z.string().nullable(),
          })
        ),
      })
    )
    .max(2000),
})
export function CandidateDocumentProgress({
  caseId,
  fileId,
  onOpenReading,
}: {
  caseId: string
  fileId: string
  onOpenReading: (mappingId: string, candidateId: string) => void
}) {
  const [opened, setOpened] = useState(false)
  const [page, setPage] = useState(0)
  const progress = useQuery({
    queryKey: ["financial-candidates", caseId, "document-progress", fileId],
    enabled: opened,
    retry: false,
    queryFn: async () => {
      const data = schema.parse(
        await fetchAPI<unknown>(
          candidateUrl(
            `candidate-sources/${encodeURIComponent(fileId)}/progress`,
            caseId
          )
        )
      )
      assertCandidateScope(data, caseId)
      if (
        data.evidence_file_id !== fileId ||
        data.pages.some((p, i) => p.page_number !== i + 1)
      )
        throw Error("Progress returned for a different document or page scope.")
      for (const status of ["pending", "resolved", "rejected"] as const) {
        if (
          data.pages.some(
            (p) =>
              p.batches.reduce((sum, b) => sum + b[status], 0) !==
              p.counts[status]
          )
        )
          throw Error("Page and batch counts disagree.")
      }
      const total = (c: z.infer<typeof counts>) =>
        c.pending + c.resolved + c.rejected
      if (
        data.pages.reduce((sum, p) => sum + total(p.counts), 0) +
          data.unlocated_readings !==
        total(data.counts)
      )
        throw Error("Document review counts disagree.")
      return data
    },
  })
  return (
    <section
      aria-label="Document review overview"
      className="space-y-3 rounded border p-3"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-semibold">Review across the whole PDF</h3>
        <Button variant="outline" onClick={() => setOpened((v) => !v)}>
          {opened ? "Hide document progress" : "Show document progress"}
        </Button>
      </div>
      {opened && (
        <>
          <Button
            variant="outline"
            disabled={progress.isFetching}
            onClick={() => void progress.refetch()}
          >
            Refresh document progress
          </Button>
          {progress.isFetching ? (
            <p role="status">Loading document progress…</p>
          ) : progress.isError ? (
            <p role="alert">
              Document progress unavailable. {progress.error.message}
            </p>
          ) : (
            progress.data && (
              <>
                <p>
                  {progress.data.filename}: {progress.data.counts.pending}{" "}
                  awaiting review · {progress.data.counts.resolved} resolved ·{" "}
                  {progress.data.counts.rejected} rejected
                </p>
                <p className="text-muted-foreground">
                  {progress.data.limitation}
                </p>
                {progress.data.unlocated_readings > 0 && (
                  <p>
                    {progress.data.unlocated_readings} saved readings could not
                    be assigned to one known page.
                  </p>
                )}
                <ul className="space-y-2">
                  {progress.data.pages
                    .slice(page * 20, page * 20 + 20)
                    .map((p) => (
                      <li key={p.page_number} className="rounded border p-2">
                        <p className="font-medium">Page {p.page_number}</p>
                        {!p.prepared && (
                          <p>Current stored table preparation unavailable.</p>
                        )}
                        {p.batches.length === 0 ? (
                          <p>
                            No saved rows selected. Check this page for
                            transactions, fees and interest.
                          </p>
                        ) : (
                          <>
                            <p>
                              {p.counts.pending} awaiting review ·{" "}
                              {p.counts.resolved} resolved · {p.counts.rejected}{" "}
                              rejected
                            </p>
                            {p.batches.map((b, i) => (
                              <div
                                key={b.mapping_id}
                                className="flex flex-wrap items-center gap-2"
                              >
                                <span>
                                  Batch {i + 1}: {b.pending} awaiting review
                                </span>
                                {b.next_pending_candidate_id && (
                                  <Button
                                    size="sm"
                                    onClick={() =>
                                      onOpenReading(
                                        b.mapping_id,
                                        b.next_pending_candidate_id!
                                      )
                                    }
                                  >
                                    Continue page {p.page_number}, batch {i + 1}
                                  </Button>
                                )}
                              </div>
                            ))}
                          </>
                        )}
                      </li>
                    ))}
                </ul>
                <div className="flex items-center gap-2">
                  <Button
                    disabled={page === 0}
                    onClick={() => setPage((p) => p - 1)}
                  >
                    Previous overview pages
                  </Button>
                  <span>
                    {page * 20 + 1}–
                    {Math.min((page + 1) * 20, progress.data.pages.length)} of{" "}
                    {progress.data.pages.length} stored page positions
                  </span>
                  <Button
                    disabled={(page + 1) * 20 >= progress.data.pages.length}
                    onClick={() => setPage((p) => p + 1)}
                  >
                    Next overview pages
                  </Button>
                </div>
              </>
            )
          )}
        </>
      )}
    </section>
  )
}
