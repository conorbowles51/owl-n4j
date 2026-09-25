import { z } from "zod"

const count = z.number().int().nonnegative()
const visibility = z.enum(["visible", "hidden"])
export const financialSourceAuditGroup = z.object({
  root_file_id: z.string(),
  current_file_id: z.string(),
  filename: z.string(),
  version_count: count,
  hidden_version_count: count,
  visibility,
  visibility_revision: z.string(),
  active_work: z.boolean(),
  retained_text_available: z.boolean(),
  provenance: z.object({
    enrollment_recorded: z.boolean(),
    explicit_selection: z.boolean(),
    preparation_mode: z.string().nullable(),
    saved_review_storage_count: count,
    review_count_basis: z.literal("storage_representations"),
    imported_source_count: count,
    saved_period_count: count,
    payment_count: count,
    note_count: count,
    batch_count: count,
    parsed_statement_period_count: count,
    recognized_readers: z.array(z.string()),
  }),
  protection_reasons: z.array(
    z.object({ code: z.string(), message: z.string() })
  ),
})
export type FinancialSourceAuditGroup = z.infer<
  typeof financialSourceAuditGroup
>
export const financialSourceAuditList = z.object({
  applied: z.literal(false),
  case_id: z.string(),
  total: count,
  offset: count,
  limit: count,
  summary: z.object({
    groups: count,
    visible: count,
    hidden: count,
    protected: count,
    active_work: count,
    with_retained_text: count,
    without_retained_text: count,
  }),
  groups: z.array(financialSourceAuditGroup),
  limitation: z.string(),
})
export const financialSourceAuditDetail = z.object({
  applied: z.literal(false),
  case_id: z.string(),
  evidence_file_id: z.string(),
  group: financialSourceAuditGroup,
  source_summary: z.string().nullish(),
  source_summary_truncated: z.boolean().default(false),
  versions: z.array(
    z.object({
      evidence_file_id: z.string(),
      filename: z.string(),
      status: z.string(),
      created_at: z.string().nullable(),
      visibility,
      selected_by: z.string().nullable(),
      selected_at: z.string().nullable(),
      preparation_mode: z.string().nullable(),
      retained_text_available: z.boolean(),
    })
  ),
  versions_truncated: z.boolean(),
  text_excerpt: z.object({
    evidence_file_id: z.string(),
    available: z.boolean(),
    offset: count,
    total_characters: count,
    text: z.string(),
    truncated: z.boolean(),
  }),
  limitation: z.string(),
})
