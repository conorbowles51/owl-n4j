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
        reason: "No stored periods or transactions to compare.",
      },
    ],
    groups: [
      {
        group_key: "group",
        members: [
          {
            document_id: "first",
            filename: "original.ofx",
            status: "admitted",
            superseded_by_id: null,
            match: "comparison_document",
            rows_by_status: { admitted: 2 },
          },
          {
            document_id: "copy",
            filename: "copy.ofx",
            status: "superseded",
            superseded_by_id: "first",
            match: "identical_reading",
            rows_by_status: { superseded: 2 },
          },
        ],
      },
    ],
  }
}
