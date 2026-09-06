import { z } from "zod"

const count = z.number().int().nonnegative().max(Number.MAX_SAFE_INTEGER)
const document = z.object({
  document_id: z.string().min(1),
  filename: z.string(),
  status: z.string().min(1),
  superseded_by_id: z.string().nullable(),
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
  groups: z.array(
    z.object({
      group_key: z.string().min(1),
      members: z
        .array(
          reviewedDocument.extend({
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

export function readDuplicateCandidates(
  value: unknown,
  caseId: string
): DuplicateCandidates {
  const result = schema.safeParse(value)
  if (!result.success)
    throw new Error("The duplicate comparison response is incomplete.")
  const data = result.data
  const members = data.groups.flatMap((group) => group.members)
  const ids = [...members, ...data.skipped].map((row) => row.document_id)
  if (
    data.case_id !== caseId ||
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
    comparison_document: "Compared against this document",
    identical_bytes: "Same file bytes and stored reading",
    identical_reading: "Same stored reading; different files",
    same_file_different_reading: "Same file bytes; conflicting stored readings",
    shared_coverage: "Shared account or period coverage; different readings",
  }
  return labels[match] ?? `Unrecognised match (${match})`
}
