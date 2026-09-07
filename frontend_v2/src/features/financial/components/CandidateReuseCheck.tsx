import { useMutation } from "@tanstack/react-query"
import { z } from "zod"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import {
  assertCandidateScope,
  candidateStatus,
  candidateUrl,
} from "../lib/candidate-contract"
const count = z.number().int().nonnegative()
const reference = z.object({
  candidate_id: z.string(),
  mapping_id: z.string(),
  row_index: count,
  status: candidateStatus,
})
const resultSchema = z.object({
  case_id: z.string(),
  evidence_file_id: z.string(),
  counts: z.object({ pending: count, resolved: count, rejected: count }),
  active_readings: count,
  pairs_examined: count,
  total_pairs: count,
  comparison_complete: z.boolean(),
  source_reuse_pairs: count,
  unavailable_pairs: count,
  findings: z.array(
    z.object({
      kind: z.enum([
        "same_stored_row",
        "overlapping_source_area",
        "overlapping_source_text",
        "comparison_unavailable",
      ]),
      left: reference,
      right: reference,
    })
  ),
  findings_truncated: z.boolean(),
  revision: z.string().regex(/^[a-f0-9]{64}$/),
  applied: z.literal(false),
  scope: z.string(),
  limitation: z.string(),
})
const descriptions = {
  same_stored_row: "The same stored row was selected more than once.",
  overlapping_source_area:
    "Source areas overlap; inspect whether the readings reuse the same evidence.",
  overlapping_source_text: "These readings reuse some of the same source text.",
  comparison_unavailable: "These source locations cannot be reliably compared.",
}
export function CandidateReuseCheck({
  caseId,
  fileId,
  onOpenReading,
}: {
  caseId: string
  fileId: string
  onOpenReading: (mappingId: string, candidateId: string) => void
}) {
  const check = useMutation({
    retry: false,
    mutationFn: async () => {
      const data = resultSchema.parse(
        await fetchAPI<unknown>(
          candidateUrl(
            `candidate-sources/${encodeURIComponent(fileId)}/reuse-check`,
            caseId
          )
        )
      )
      assertCandidateScope(data, caseId)
      if (
        data.evidence_file_id !== fileId ||
        data.pairs_examined > data.total_pairs ||
        data.comparison_complete !== (data.pairs_examined === data.total_pairs)
      )
        throw new Error(
          "The source check does not match this PDF or its stated coverage."
        )
      return data
    },
  })
  return (
    <section
      aria-label="Check repeated PDF sources"
      className="space-y-2 rounded border p-3"
    >
      <h3 className="font-semibold">Check repeated source rows</h3>
      <p>
        Compare pending and resolved readings saved from this PDF across all
        batches. Rejected readings stay in history and are not compared. This
        does not decide whether two economic transactions are duplicates.
      </p>
      <Button
        variant="outline"
        disabled={check.isPending}
        onClick={() => {
          check.reset()
          check.mutate()
        }}
      >
        Check source reuse
      </Button>
      {check.isPending && <p role="status">Checking saved source locations…</p>}
      {check.isError && (
        <p role="alert">
          Source check could not be completed. {check.error.message}
        </p>
      )}
      {check.data && (
        <div className="space-y-2">
          <p>
            {check.data.counts.pending} pending · {check.data.counts.resolved}{" "}
            resolved · {check.data.counts.rejected} rejected.
          </p>
          <p>
            {check.data.pairs_examined} of {check.data.total_pairs} reading
            pairs compared. {check.data.source_reuse_pairs} possible source
            reuses; {check.data.unavailable_pairs} pairs could not be located
            well enough to compare.
          </p>
          {!check.data.comparison_complete && (
            <p role="alert">
              Comparison limit reached. This is an incomplete check.
            </p>
          )}
          {check.data.findings_truncated && (
            <p>
              Showing the first {check.data.findings.length} findings; the
              counts above include all findings in the compared pairs.
            </p>
          )}
          <ul className="space-y-2">
            {check.data.findings.map((finding, i) => (
              <li key={i} className="space-y-1 rounded border p-2">
                <p>{descriptions[finding.kind]}</p>
                <div className="flex flex-wrap gap-2">
                  {[finding.left, finding.right].map((item, index) => (
                    <Button
                      key={index}
                      variant="outline"
                      size="sm"
                      onClick={() =>
                        onOpenReading(item.mapping_id, item.candidate_id)
                      }
                    >
                      Open {index === 0 ? "first" : "second"} reading: source
                      row {item.row_index + 1} ({item.status})
                    </Button>
                  ))}
                </div>
              </li>
            ))}
          </ul>
          <p className="text-xs text-muted-foreground">
            Snapshot only: run the check again after changing reviews. No
            reading has been rejected, merged or admitted by this check.
          </p>
        </div>
      )}
    </section>
  )
}
