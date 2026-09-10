import { z } from "zod"
import { sourceTable } from "./pdf-source-table"
const index = z.number().int().nonnegative()
const digest = z.string().regex(/^[a-f0-9]{64}$/)
const meaning = z.enum([
  "unknown",
  "date",
  "booking_date",
  "transaction_date",
  "value_date",
  "amount",
  "debit",
  "credit",
  "description",
  "reference",
  "balance",
  "account",
  "currency",
  "direction",
])
const cell = z.object({
  column_index: index,
  expected_text: z.string(),
  locator: z.unknown(),
  proposed_meaning: meaning,
})
export const pdfModelNomination = z
  .object({
    id: z.string().uuid(),
    case_id: z.string().uuid(),
    evidence_file_id: z.string().uuid(),
    status: z.enum(["pending", "completed", "failed"]),
    request: z.object({
      schema_version: z.literal("pdf-cell-nomination-v1"),
      execution_mode: z.enum(["configured_provider", "simulated_test"]),
      page_number: z.number().int().positive(),
      table_index: index,
      source_revision: digest,
      case_id: z.string().uuid(),
      evidence_file_id: z.string().uuid(),
      provider: z.string(),
      model_id: z.string(),
      prompt_sha256: digest,
    }),
    request_sha256: digest,
    result: z
      .object({
        transport: z
          .discriminatedUnion("status", [
            z.object({
              schema_version: z.literal("loupe.pdf_model_transport/1"),
              status: z.literal("captured"),
              request_arguments: z.record(z.string(), z.unknown()),
              request_arguments_sha256: digest,
              adapter_sha256: digest,
              response_metadata: z.object({
                reported_model: z.string().max(256).optional(),
                response_id: z.string().max(256).optional(),
              }),
              limitation: z.string(),
            }),
            z.object({
              schema_version: z.literal("loupe.pdf_model_transport/1"),
              status: z.literal("unavailable"),
              reason: z.string(),
              limitation: z.string(),
            }),
          ])
          .optional(),
        rows: z
          .array(
            z.object({
              row_index: index,
              reason: z.string(),
              cells: z.array(cell).max(64),
            })
          )
          .max(200),
        raw_response_sha256: digest,
        usage: z.record(z.string(), index),
        source_revision: digest,
        prompt_version: z.literal("pdf-cell-nomination-v1"),
      })
      .nullable(),
    error_code: z.string().nullable(),
    created_at: z.string(),
    completed_at: z.string().nullable(),
    applied: z.literal(false),
    limitation: z.string(),
  })
  .refine(
    (v) =>
      v.case_id === v.request.case_id &&
      v.evidence_file_id === v.request.evidence_file_id &&
      (v.status === "completed"
        ? v.result !== null &&
          v.error_code === null &&
          v.completed_at !== null &&
          v.result.source_revision === v.request.source_revision
        : v.result === null &&
          (v.status === "pending"
            ? v.error_code === null && v.completed_at === null
            : v.error_code !== null && v.completed_at !== null))
  )
export type PdfModelNomination = z.infer<typeof pdfModelNomination>
export function modelNominationPlans(
  run: PdfModelNomination,
  selected: number[],
  raw: unknown
) {
  const source = sourceTable.parse(raw)
  if (
    run.status !== "completed" ||
    !run.result ||
    !selected.length ||
    new Set(selected).size !== selected.length
  )
    throw Error("Choose distinct rows from a completed model attempt.")
  if (
    run.case_id !== source.case_id ||
    run.evidence_file_id !== source.evidence_file_id ||
    run.request.page_number !== source.page_number ||
    run.request.table_index !== source.table_index ||
    run.request.source_revision !== source.source_revision
  )
    throw Error("Source changed. Reload before saving these model proposals.")
  const groups = new Map<
    string,
    {
      columns: { column_index: number; meaning: string }[]
      rows: {
        row_index: number
        cells: { column_index: number; expected_text: string }[]
      }[]
    }
  >()
  if (
    new Set(run.result.rows.map((r) => r.row_index)).size !==
    run.result.rows.length
  )
    throw Error("Model row positions are repeated.")
  for (const index of [...selected].sort((a, b) => a - b)) {
    const row = run.result.rows.find((r) => r.row_index === index),
      original = source.rows.find((r) => r.row_index === index)
    if (
      !row ||
      !original ||
      row.cells.length !== original.cells.length ||
      new Set(row.cells.map((c) => c.column_index)).size !== row.cells.length ||
      row.cells.some(
        (c) =>
          original.cells.filter(
            (o) =>
              o.column_index === c.column_index &&
              o.expected_text === c.expected_text
          ).length !== 1
      )
    )
      throw Error("A model proposal differs from its original source cells.")
    const columns = [...source.columns]
      .sort((a, b) => a - b)
      .map((column_index) => ({
        column_index,
        meaning:
          row.cells.find((c) => c.column_index === column_index)
            ?.proposed_meaning ?? "unknown",
      }))
    const key = JSON.stringify(columns),
      group = groups.get(key) ?? { columns, rows: [] }
    group.rows.push({
      row_index: index,
      cells: original.cells
        .map(({ column_index, expected_text }) => ({
          column_index,
          expected_text,
        }))
        .sort((a, b) => a.column_index - b.column_index),
    })
    groups.set(key, group)
  }
  return [...groups.values()].map((group) => ({
    schema_version: "pdf-grid-mapping-v1",
    case_id: source.case_id,
    evidence_file_id: source.evidence_file_id,
    page_number: source.page_number,
    table_index: source.table_index,
    source_revision: source.source_revision,
    nomination_id: run.id,
    ...group,
  }))
}
