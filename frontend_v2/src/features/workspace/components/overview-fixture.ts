import type { WorkspaceOverviewResponse } from "../api"

export const overview: WorkspaceOverviewResponse = {
  case_id: "case-1",
  as_of: "2026-09-02T12:00:00Z",
  timezone: "Europe/Dublin",
  shared_attention: [
    {
      attention_key: "deadline:deadline-1:deadline_overdue:v1",
      source_type: "deadline",
      source_id: "deadline-1",
      reason_code: "deadline_overdue",
      reason_label: "Deadline overdue",
      rank: 1,
      priority_band: 0,
      title: "Disclosure response",
      due_at: "2026-09-01T00:00:00+01:00",
      href: "/cases/case-1/workspace?view=work&item=deadline-1",
      metadata: {},
    },
  ],
  personal_attention: [
    {
      attention_key: "task:task-1:task_urgent:v2",
      source_type: "task",
      source_id: "task-1",
      reason_code: "task_urgent",
      reason_label: "Urgent task",
      rank: 1,
      priority_band: 0,
      title: "Review account statement",
      summary: "Resolve the unexplained transfer.",
      href: "/cases/case-1/workspace?view=work&item=task-1",
      metadata: {},
    },
  ],
  context: {
    case_summary: "Cross-border asset tracing investigation",
    background: "A disclosure raised questions about beneficial control.",
    investigation_type: "Asset tracing",
    jurisdiction: "Ireland",
    mandate_complete: true,
    mandate: {
      id: "mandate-1",
      version_number: 2,
      objective: "Trace the disputed transfers",
      key_questions: ["Who controlled the destination account?"],
    },
  },
  recent_casework: [
    {
      id: "entry-1",
      entry_type: "finding",
      title: "Control was retained",
      summary: "Signing authority remained unchanged.",
      review_state: "pending",
      href: "/cases/case-1/workspace?view=casework&entry=entry-1",
    },
  ],
  dossier_highlights: [
    {
      id: "dossier-1",
      display_name: "Henry Example",
      dossier_type: "person",
      summary: "Account signatory and company director.",
      importance: "high",
      needs_link_review: false,
      href: "/cases/case-1/dossiers?dossier=dossier-1",
    },
  ],
  pinned_evidence: [
    {
      id: "pin-1",
      item_type: "evidence",
      item_id: "evidence-1",
      evidence_file_id: "evidence-1",
      filename: "account-statement.pdf",
      pinned_by_name: "Case Owner",
    },
  ],
  bounded: true,
  limits: { shared_attention: 12, personal_attention: 12 },
}
