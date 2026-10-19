import type { FinancialSourceAuditGroup } from "../lib/financial-source-audit"

export function auditGroup(index = 0): FinancialSourceAuditGroup {
  return {
    root_file_id: `source-${index}`,
    current_file_id: `reading-${index}`,
    filename:
      index < 2 ? "Shared name.txt" : `Synthetic source ${index}.custom`,
    version_count: 2,
    hidden_version_count: index === 2 ? 2 : 0,
    visibility: index === 2 ? "hidden" : "visible",
    visibility_revision: "initial",
    active_work: index === 1,
    retained_text_available: index !== 2,
    provenance: {
      enrollment_recorded: true,
      explicit_selection: index === 1,
      preparation_mode: "pdf_review",
      saved_review_storage_count: 1,
      review_count_basis: "storage_representations",
      imported_source_count: index === 1 ? 1 : 0,
      saved_period_count: index === 1 ? 2 : 0,
      payment_count: index === 1 ? 10 : 0,
      note_count: 0,
      batch_count: 1,
      parsed_statement_period_count: 1,
      recognized_readers: index === 1 ? ["synthetic_statement_reader"] : [],
    },
    protection_reasons:
      index === 1
        ? [
            {
              code: "active_work",
              message: "Reading, preparation or import is queued or active.",
            },
            {
              code: "saved_financial_records",
              message: "Saved financial records or their history are retained.",
            },
          ]
        : [
            {
              code: "saved_review",
              message: "Saved review or correction work is retained.",
            },
          ],
  }
}

export function auditList(
  groups: FinancialSourceAuditGroup[],
  visibility = "visible",
  offset = 0,
  caseId = "case"
) {
  const selected = groups.filter(
    (group) => visibility === "all" || group.visibility === visibility
  )
  return {
    applied: false,
    case_id: caseId,
    total: selected.length,
    offset,
    limit: 50,
    summary: {
      groups: groups.length,
      visible: groups.filter((group) => group.visibility === "visible").length,
      hidden: groups.filter((group) => group.visibility === "hidden").length,
      protected: groups.filter((group) => group.protection_reasons.length)
        .length,
      active_work: groups.filter((group) => group.active_work).length,
      with_retained_text: groups.filter(
        (group) => group.retained_text_available
      ).length,
      without_retained_text: groups.filter(
        (group) => !group.retained_text_available
      ).length,
    },
    groups: selected.slice(offset, offset + 50),
    limitation:
      "Recorded provenance is not a content classification. Counts include retained history.",
  }
}

export function auditDetail(
  group: FinancialSourceAuditGroup,
  fileId = group.current_file_id,
  offset = 0,
  caseId = "case"
) {
  const available =
    group.retained_text_available && fileId === group.current_file_id
  return {
    applied: false,
    case_id: caseId,
    evidence_file_id: fileId,
    group,
    source_summary: "Synthetic stored summary for source inspection.",
    source_summary_truncated: false,
    versions: [group.root_file_id, group.current_file_id].map((id, index) => ({
      evidence_file_id: id,
      filename: group.filename,
      status: "processed",
      created_at: `2026-09-${20 + index}T12:00:00Z`,
      visibility: group.visibility,
      selected_by: group.provenance.explicit_selection
        ? "synthetic-user"
        : null,
      selected_at: group.provenance.explicit_selection
        ? "2026-09-20T12:00:00Z"
        : null,
      preparation_mode: index ? "pdf_review" : "full",
      retained_text_available: index === 1 && available,
    })),
    versions_truncated: false,
    text_excerpt: {
      evidence_file_id: fileId,
      available,
      offset,
      total_characters: available ? 6000 : 0,
      text: available
        ? offset
          ? "Later retained text, still from the selected reading."
          : "Synthetic retained text. <script>this is source text, never executable</script>"
        : "",
      truncated: available && offset === 0,
    },
    limitation:
      "This is retained extracted text, not a new reading or a determination of financial relevance.",
  }
}
