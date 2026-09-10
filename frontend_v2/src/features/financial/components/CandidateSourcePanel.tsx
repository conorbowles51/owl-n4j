import { StatementLayoutContextPanel } from "./StatementLayoutContextPanel"
import {
  layoutContext,
  type LayoutCitation,
} from "../lib/statement-layout-context"
import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { z } from "zod"
import { fetchAPI } from "@/lib/api-client"
import { Button } from "@/components/ui/button"
import { candidateUrl, type CandidateReview } from "../lib/candidate-contract"
import { TransactionSourceHighlight } from "./TransactionSourceHighlight"
const source = z.object({
  case_id: z.string(),
  candidate_id: z.string(),
  mapping_id: z.string(),
  evidence_file_id: z.string(),
  review_revision: z.string(),
  layout_context: layoutContext.nullable().optional(),
  applied: z.literal(false),
  cells: z.array(
    z.object({
      column_index: z.number().int().nonnegative(),
      proposed_meaning: z.string(),
      text: z.string(),
      locator: z.unknown(),
    })
  ),
})
export function CandidateSourcePanel({
  caseId,
  mappingId,
  fileId,
  review,
}: {
  caseId: string
  mappingId: string
  fileId: string
  review: CandidateReview
}) {
  const [contextCell, setContextCell] = useState<LayoutCitation | null>(null)
  const [selected, setSelected] = useState<number | null>(null)
  const query = useQuery({
    queryKey: [
      "financial-candidates",
      caseId,
      "source-readings",
      review.candidate_id,
      review.review_revision,
    ],
    retry: false,
    refetchOnWindowFocus: false,
    queryFn: async () => {
      const data = source.parse(
        await fetchAPI(
          candidateUrl(
            `candidates/${review.candidate_id}/source-readings`,
            caseId
          )
        )
      )
      if (
        data.case_id !== caseId ||
        data.mapping_id !== mappingId ||
        data.evidence_file_id !== fileId ||
        data.candidate_id !== review.candidate_id ||
        data.review_revision !== review.review_revision ||
        data.cells.length !== review.original.cells.length ||
        new Set(data.cells.map((c) => c.column_index)).size !==
          data.cells.length ||
        data.cells.some((c) => {
          const old = review.original.cells.find(
            (v) => v.column_index === c.column_index
          )
          return (
            !old ||
            c.text !== (old.text ?? old.source?.text) ||
            c.proposed_meaning !== old.proposed_meaning
          )
        })
      )
        throw Error(
          "Source readings changed or do not match this review. Reload before proceeding."
        )
      return data
    },
  })
  const cell = contextCell
    ? {
        column_index: contextCell.column_index,
        text: contextCell.expected_text,
        locator: contextCell.locator,
      }
    : (query.data?.cells.find((c) => c.column_index === selected) ??
      query.data?.cells[0])
  return (
    <section
      aria-label="Original document beside review"
      className="space-y-3 rounded border p-3 lg:sticky lg:top-3"
    >
      <h4 className="font-semibold">Original document</h4>
      <p>
        Select an original value to see its recorded location. Column meanings
        remain proposals; a highlight does not verify the reading.
      </p>
      {query.isPending && <p role="status">Loading original source…</p>}
      {query.isError && (
        <>
          <p role="alert">{query.error.message}</p>
          <Button variant="outline" onClick={() => void query.refetch()}>
            Reload original source
          </Button>
        </>
      )}
      {query.data && !query.isError && !query.isFetching && (
        <>
          {query.data.layout_context && (
            <StatementLayoutContextPanel
              context={query.data.layout_context}
              onSource={setContextCell}
            />
          )}
          <div className="flex flex-wrap gap-2">
            {query.data.cells.map((c) => (
              <Button
                key={c.column_index}
                variant={
                  !contextCell && cell?.column_index === c.column_index
                    ? "secondary"
                    : "outline"
                }
                aria-pressed={
                  !contextCell && cell?.column_index === c.column_index
                }
                onClick={() => {
                  setContextCell(null)
                  setSelected(c.column_index)
                }}
              >
                Source column {c.column_index + 1}:{" "}
                {c.proposed_meaning.replaceAll("_", " ")}
              </Button>
            ))}
          </div>
          {cell && (
            <>
              <p className="whitespace-pre-wrap break-words">
                <strong>Original text:</strong> {cell.text}
              </p>
              <TransactionSourceHighlight
                sourceDocumentId={fileId}
                locatorPayload={cell.locator}
                valueLabel={cell.text}
              />
            </>
          )}
          {!cell && <p>No original cells available.</p>}
        </>
      )}
    </section>
  )
}
