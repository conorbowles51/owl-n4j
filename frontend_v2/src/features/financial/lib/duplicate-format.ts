import { z } from "zod"

const count = z.number().int().nonnegative().max(Number.MAX_SAFE_INTEGER)
const statementContext = z.object({
  period_id: z.string().min(1),
  account_id: z.string().min(1),
  bank: z.string().nullable(),
  account_holder: z.string().nullable(),
  account_number: z.string().nullable(),
  currency: z.string(),
  period_start: z.string().nullable(),
  period_end: z.string().nullable(),
})
const document = z.object({
  document_id: z.string().min(1),
  filename: z.string(),
  status: z.string().min(1),
  superseded_by_id: z.string().nullable(),
  evidence_file_id: z.string().uuid().nullable().optional(),
  statement_id: z
    .string()
    .regex(/^[a-f0-9]{64}$/)
    .nullable()
    .optional(),
  statement_context: z.array(statementContext).default([]),
  rows_by_status: z.record(z.string(), count).optional(),
})
const reviewedDocument = document.extend({
  revision: z.string().regex(/^[a-f0-9]{64}$/),
})
const schema = z.object({
  case_id: z.string(),
  documents: count,
  compared: count,
  skipped: z.array(document.extend({ reason: z.string().min(1) })),
  excluded_documents: z.array(reviewedDocument),
  stored_rows_in_case: count.optional(),
  source_hash_groups: z
    .array(
      z.object({
        sha256_at_ingestion: z.string().regex(/^[a-f0-9]{64}$/),
        members: z
          .array(
            document.extend({
              source_transaction_id: z.string().nullable().optional(),
            })
          )
          .min(2),
        limitation: z.string(),
      })
    )
    .default([]),
  groups: z.array(
    z.object({
      group_key: z.string().min(1),
      members: z
        .array(
          reviewedDocument.extend({
            source_transaction_id: z.string().min(1).nullable().optional(),
            reading_fingerprint: z.string().regex(/^[a-f0-9]{64}$/),
            match: z.string().min(1),
            rows_by_status: z.record(z.string(), count),
          })
        )
        .min(2),
    })
  ),
})
export type DuplicateCandidates = z.infer<typeof schema>
export type DuplicateDocument = z.infer<typeof document>
export type DuplicateStatementContext = z.infer<typeof statementContext>

export function duplicateStatementLabel(
  row: DuplicateStatementContext
): string {
  return [
    row.bank?.trim() || "Bank not recorded",
    row.account_holder?.trim() || "Account holder not recorded",
    row.account_number?.trim()
      ? `Account ${row.account_number}`
      : "Account number not recorded",
    row.currency?.trim() || "Currency not recorded",
    `${row.period_start || "Start date not recorded"} to ${row.period_end || "End date not recorded"}`,
  ].join(" · ")
}

export function duplicateRowsLabel(
  rows: DuplicateDocument["rows_by_status"]
): string {
  if (!rows) return "Stored row count unavailable"
  return (
    Object.entries(rows)
      .map(
        ([status, amount]) =>
          `${amount} ${
            (
              {
                admitted: "included rows",
                superseded: "excluded or corrected rows",
                quarantined: "rows needing review",
                rejected: "rejected rows",
              } as Record<string, string>
            )[status] || `${status} rows`
          }`
      )
      .join(" · ") || "0 stored rows"
  )
}

export function readDuplicateCandidates(
  value: unknown,
  caseId: string
): DuplicateCandidates {
  const result = schema.safeParse(value)
  if (!result.success)
    throw new Error("The duplicate comparison response is incomplete.")
  const data = result.data
  const members = data.groups.flatMap((group) => group.members)
  const documents = [
    ...members,
    ...data.skipped,
    ...data.excluded_documents,
    ...data.source_hash_groups.flatMap((group) => group.members),
  ]
  const ids = [...members, ...data.skipped].map((row) => row.document_id)
  if (
    data.case_id !== caseId ||
    documents.some(
      (row) =>
        new Set(row.statement_context.map((period) => period.period_id))
          .size !== row.statement_context.length
    ) ||
    new Set(data.source_hash_groups.map((g) => g.sha256_at_ingestion)).size !==
      data.source_hash_groups.length ||
    data.source_hash_groups.some(
      (g) =>
        new Set(g.members.map((r) => r.document_id)).size !== g.members.length
    ) ||
    new Set(
      data.source_hash_groups.flatMap((g) =>
        g.members.map((r) => r.document_id)
      )
    ).size !==
      data.source_hash_groups.reduce((n, g) => n + g.members.length, 0) ||
    data.source_hash_groups.reduce((n, g) => n + g.members.length, 0) >
      data.documents ||
    data.excluded_documents.some((row) => row.status !== "superseded") ||
    new Set(data.excluded_documents.map((row) => row.document_id)).size !==
      data.excluded_documents.length ||
    data.excluded_documents.length > data.documents ||
    data.compared + data.skipped.length !== data.documents ||
    members.length > data.compared ||
    new Set(ids).size !== ids.length ||
    new Set(data.groups.map((group) => group.group_key)).size !==
      data.groups.length ||
    data.groups.some(
      (group) =>
        group.members.filter((row) => row.match === "comparison_document")
          .length !== 1
    )
  ) {
    throw new Error(
      "The duplicate comparison does not agree with its case or coverage."
    )
  }
  return data
}

export function duplicateMatchLabel(match: string): string {
  const labels: Record<string, string> = {
    comparison_document:
      "The other files in this group are compared with this file",
    identical_bytes: "Same original file and transaction values",
    identical_reading:
      "Same transaction values and statement balances; different files",
    same_file_different_reading:
      "Same original file, but the saved transaction values differ",
    shared_coverage:
      "Same account or dates, but the saved transaction values differ",
  }
  return labels[match] ?? `Unrecognised match (${match})`
}
