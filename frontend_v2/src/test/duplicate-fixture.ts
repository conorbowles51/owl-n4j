import type { DuplicateCandidates } from "@/features/financial/lib/duplicate-format"
export function duplicateCandidates(caseId = "case-1"): DuplicateCandidates {
  return {
    case_id: caseId,
    documents: 3,
    compared: 2,
    skipped: [
      {
        document_id: "empty",
        filename: "empty.pdf",
        status: "admitted",
        superseded_by_id: null,
        statement_context: [],
        reason: "No stored periods or transactions to compare.",
      },
    ],
    excluded_documents: [],
    source_hash_groups: [],
    groups: [
      {
        group_key: "group",
        members: [
          {
            document_id: "first",
            filename: "original.ofx",
            status: "admitted",
            superseded_by_id: null,
            statement_context: [],
            revision: "a".repeat(64),
            reading_fingerprint: "b".repeat(64),
            match: "comparison_document",
            rows_by_status: { admitted: 2 },
          },
          {
            document_id: "copy",
            filename: "copy.ofx",
            status: "superseded",
            superseded_by_id: "first",
            statement_context: [],
            revision: "a".repeat(64),
            reading_fingerprint: "b".repeat(64),
            match: "identical_reading",
            rows_by_status: { superseded: 2 },
          },
        ],
      },
    ],
  }
}

export function duplicateContextCandidates(groups = 12): DuplicateCandidates {
  const data = duplicateCandidates()
  data.documents = groups * 2
  data.compared = data.documents
  data.skipped = []
  data.groups = Array.from({ length: groups }, (_, group) => ({
    group_key: `context-group-${group}`,
    members: [0, 1].map(
      (copy): DuplicateCandidates["groups"][number]["members"][number] => ({
        ...data.groups[0].members[copy],
        document_id: `context-${group}-${copy}`,
        superseded_by_id: copy ? `context-${group}-0` : null,
        filename: "Monthly statements.txt",
        evidence_file_id: `10000000-0000-4000-8000-${String(group * 2 + copy).padStart(12, "0")}`,
        statement_id: "c".repeat(64),
        rows_by_status:
          group === groups - 1
            ? {}
            : copy
              ? { superseded: 3 }
              : { admitted: 3 },
        source_transaction_id: null,
        statement_context: [1, 2].map((month) => ({
          period_id: `period-${group}-${copy}-${month}`,
          account_id: `account-${group}`,
          bank: "Example Bank",
          account_holder: `Synthetic company ${group + 1}`,
          account_number: `0012${String(group).padStart(4, "0")}`,
          currency: "USD",
          period_start: `2026-0${month}-01`,
          period_end: `2026-0${month}-${month === 1 ? 31 : 28}`,
        })),
      })
    ),
  }))
  return data
}
