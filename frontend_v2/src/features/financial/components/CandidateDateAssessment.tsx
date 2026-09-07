import { useMutation } from "@tanstack/react-query"
import { z } from "zod"
import { fetchAPI } from "@/lib/api-client"
import { Button } from "@/components/ui/button"
import { candidateUrl, assertCandidateScope } from "../lib/candidate-contract"
import { TransactionSourceHighlight } from "./TransactionSourceHighlight"

const answer = z.object({
  case_id: z.string(),
  candidate_id: z.string(),
  mapping_id: z.string(),
  review_revision: z.string(),
  assessment_revision: z.string().regex(/^[a-f0-9]{64}$/),
  applied: z.literal(false),
  limitation: z.string(),
  date_cells: z.array(
    z
      .object({
        column_index: z.number().int().nonnegative(),
        proposed_meaning: z.string(),
        source: z.object({
          text: z.string(),
          locator: z.unknown().optional(),
          page_number: z.number().int().positive().nullable().optional(),
        }),
        assessment: z.object({
          raw: z.string(),
          origin: z.string(),
          status: z.enum([
            "unsupported",
            "invalid_calendar_date",
            "unambiguous_format",
            "ambiguous_order",
            "missing_year",
            "ambiguous_century",
          ]),
          requires_source_review: z.literal(true),
          explanation: z.string(),
          glyph_limitation: z.string(),
          proposals: z.array(
            z
              .object({
                order: z.string(),
                iso_date: z
                  .string()
                  .regex(/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/)
                  .optional(),
                month: z.number().int().min(1).max(12).optional(),
                day: z.number().int().min(1).max(31).optional(),
              })
              .refine((p) =>
                p.iso_date !== undefined
                  ? p.month === undefined && p.day === undefined
                  : p.month !== undefined && p.day !== undefined
              )
          ),
        }),
      })
      .refine((cell) => cell.source.text === cell.assessment.raw)
  ),
  unclassified_columns: z.array(z.number().int().nonnegative()),
})

export function CandidateDateAssessment({
  caseId,
  candidateId,
  mappingId,
  fileId,
  reviewRevision,
}: {
  caseId: string
  candidateId: string
  mappingId: string
  fileId: string
  reviewRevision: string
}) {
  const assessment = useMutation({
    retry: false,
    mutationFn: async () => {
      const data = answer.parse(
        await fetchAPI<unknown>(
          candidateUrl(
            `candidates/${encodeURIComponent(candidateId)}/date-assessment`,
            caseId
          )
        )
      )
      assertCandidateScope(data, caseId)
      if (
        data.candidate_id !== candidateId ||
        data.mapping_id !== mappingId ||
        data.review_revision !== reviewRevision
      )
        throw new Error(
          "This reading changed. Reload its review before assessing dates."
        )
      return data
    },
  })
  return (
    <section
      className="space-y-3 rounded border p-3"
      aria-label="Original date assessment"
    >
      <Button
        variant="outline"
        disabled={assessment.isPending}
        onClick={() => assessment.mutate()}
      >
        Assess original dates
      </Button>
      {assessment.isPending && (
        <p role="status">Checking original date text…</p>
      )}
      {assessment.isError && (
        <p role="alert">
          Date assessment unavailable. {assessment.error.message}
        </p>
      )}
      {assessment.isSuccess && (
        <>
          <p>{assessment.data.limitation}</p>
          {assessment.data.date_cells.length === 0 && (
            <p>
              No columns have a proposed date meaning. No other cells were
              interpreted as dates.
            </p>
          )}
          {assessment.data.date_cells.map((cell) => (
            <div key={cell.column_index} className="space-y-2">
              <p>
                Original {cell.proposed_meaning.replaceAll("_", " ")}:{" "}
                {cell.source.text}
              </p>
              <p>{cell.assessment.explanation}</p>
              <p>{cell.assessment.glyph_limitation}</p>
              {cell.assessment.proposals.map((proposal, index) => (
                <p key={index}>
                  Possible {proposal.order} reading:{" "}
                  {proposal.iso_date ??
                    `month ${proposal.month}, day ${proposal.day}; full year unresolved`}
                  .
                </p>
              ))}
              <TransactionSourceHighlight
                sourceDocumentId={fileId}
                locatorPayload={
                  cell.source.locator ??
                  (cell.source.page_number
                    ? { kind: "page_only", page: cell.source.page_number }
                    : { kind: "unlocated" })
                }
                valueLabel={cell.source.text}
              />
            </div>
          ))}
          {assessment.data.unclassified_columns.length > 0 && (
            <p>Columns with unknown meanings were not interpreted as dates.</p>
          )}
        </>
      )}
    </section>
  )
}
