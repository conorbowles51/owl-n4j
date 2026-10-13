import { z } from "zod"
import { fetchAPI } from "@/lib/api-client"

const retained = z.object({
  evidence_file_id: z.string().nullish(),
  filename: z.string(),
})

export const batchStartPreview = z.object({
  case_id: z.string(),
  selected_files: z.number().int().nonnegative(),
  suggested_batch_id: z.string().nullable(),
  open_batches: z.array(
    z.object({
      id: z.string(),
      created_at: z.string(),
      status: z.string(),
      created_by: z.string().default(""),
      file_count: z.number().int().nonnegative(),
      shared_files: z.number().int().nonnegative(),
      selected_files: z.number().int().nonnegative(),
      covers_selection: z.boolean(),
      other_files: z.array(z.string()),
      unfinished_statements: z.number().int().nonnegative(),
      files_reading: z.number().int().nonnegative(),
    })
  ),
  copies: z.array(
    z.object({
      file_id: z.string(),
      filename: z.string(),
      findings: z.array(
        z.object({
          kind: z.enum([
            "identical_bytes_in_financial",
            "identical_bytes_in_selection",
            "statements_already_copies",
          ]),
          statements: z.number().int().nonnegative().optional(),
          copies: z.number().int().nonnegative().optional(),
          retained: z.array(retained),
        })
      ),
    })
  ),
})
export type BatchStartPreview = z.infer<typeof batchStartPreview>
export type OpenBatch = BatchStartPreview["open_batches"][number]
export type BatchStartChoiceValue = "continue" | "new"

const prefix = "/api/financial/statement-import/batches"

export async function previewBatchStart(caseId: string, fileIds: string[]) {
  const result = batchStartPreview.parse(
    await fetchAPI(`${prefix}/preview?case_id=${caseId}`, {
      method: "POST",
      body: { file_ids: fileIds },
    })
  )
  if (result.case_id !== caseId)
    throw Error("The selection check belongs to another case.")
  return result
}

/** Does the preview hold anything the investigator should decide or know first? */
export function needsBatchStartChoice(preview: BatchStartPreview | null) {
  return !!preview && (!!preview.open_batches.length || !!preview.copies.length)
}

/** Files whose every known statement is a copy, or whose bytes match a kept file. */
export function wholeCopyFileIds(preview: BatchStartPreview) {
  return preview.copies
    .filter((file) =>
      file.findings.some(
        (finding) =>
          finding.kind !== "statements_already_copies" ||
          (!!finding.statements && finding.copies === finding.statements)
      )
    )
    .map((file) => file.file_id)
}

async function createBatch(
  caseId: string,
  fileIds: string[],
  requestId: string,
  startNew: boolean
) {
  const batch = z.object({ id: z.string(), case_id: z.string() }).parse(
    await fetchAPI(`${prefix}?case_id=${caseId}`, {
      method: "POST",
      body: {
        request_id: requestId,
        file_ids: fileIds,
        folder_ids: [],
        start_new: startNew,
      },
    })
  )
  if (batch.case_id !== caseId)
    throw Error("The batch belongs to another case.")
  return batch.id
}

/**
 * Start (or continue) preparation for a statement selection. Returns the
 * batch to open.
 *
 * - no choice (nothing open holds these files): an ordinary new batch;
 * - "continue": open the suggested batch; files it does not hold go into a
 *   new batch of their own, so nothing selected is left behind;
 * - "new": a fresh batch for every selected file, even those already in an
 *   unfinished batch (an explicit choice).
 */
export async function startStatementBatch({
  caseId,
  fileIds,
  requestId,
  preview,
  choice,
}: {
  caseId: string
  fileIds: string[]
  requestId: string
  preview: BatchStartPreview | null
  choice?: BatchStartChoiceValue
}) {
  const suggested = preview?.open_batches.find(
    (batch) => batch.id === preview.suggested_batch_id
  )
  if (choice === "new" || !suggested)
    return createBatch(caseId, fileIds, requestId, choice === "new")
  const others = fileIds.filter((id) => suggested.other_files.includes(id))
  // The request id is unused by the continued batch; reusing it keeps a
  // retry from preparing the other files twice.
  if (others.length) await createBatch(caseId, others, requestId, true)
  return suggested.id
}
