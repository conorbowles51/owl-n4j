import { z } from "zod"

/** Response shapes of the phone screens (03 sections 4.2 to 4.5), validated like financial's source citations. */

export const IdentifierSchema = z.object({
  kind: z.string(),
  display: z.string(),
  subkind: z.string().nullable().optional(),
  captured: z.string().nullable().optional(),
  normalised: z.boolean().optional(),
})

export const ParticipantLabelSchema = z.object({
  identity_key: z.string().nullable(),
  name: z.string().nullable(),
  name_basis: z.enum(["contact_on_this_phone", "name_in_record", "case_person", "none"]),
  identifier: IdentifierSchema.nullable(),
  is_owner: z.boolean(),
  owner_basis: z.string().nullable(),
  phone_label: z.string().nullable().optional(),
  case_names: z.array(z.object({ phone_label: z.string(), name: z.string() })),
})
export type ParticipantLabelData = z.infer<typeof ParticipantLabelSchema>

export const TimeBlockSchema = z.object({
  instant: z.string().nullable(),
  row: z.string(),
  full: z.string(),
  offset_present: z.boolean(),
  time_field: z.string().nullable().optional(),
})

export const AttachmentSchema = z.object({
  file_uid: z.string().nullable(),
  filename: z.string().nullable(),
  category: z.string().nullable(),
  verification: z.string().nullable(),
  mechanism: z.string(),
})

export const StreamRowSchema = z.object({
  event_uid: z.string(),
  record_uid: z.string(),
  kind: z.enum(["message", "call", "email", "voicemail", "chat_activity"]),
  phone: z.object({ extraction_id: z.string(), label: z.string() }),
  app: z.string().nullable(),
  thread: z.object({ thread_key: z.string(), title: z.string().nullable() }).nullable(),
  direction: z.string(),
  time: TimeBlockSchema,
  from: ParticipantLabelSchema.nullable(),
  to: z.array(ParticipantLabelSchema),
  body: z.string().nullable(),
  subject: z.string().nullable(),
  call: z
    .object({ duration_s: z.number().nullable(), status: z.string().nullable(), video: z.boolean().nullable(), words: z.string().nullable() })
    .nullable(),
  attachments: z.array(AttachmentSchema),
  flags: z.array(z.string()),
  copies: z.object({ count: z.number(), record_uids: z.array(z.string()), apps: z.array(z.string().nullable()) }),
  owner_read: z.object({ date_read: z.string().nullable(), date_played: z.string().nullable() }),
  interpretation_level: z.string(),
  line: z.string(),
})
export type StreamRow = z.infer<typeof StreamRowSchema>

export const LimitSchema = z.object({
  kind: z.string(),
  shown: z.number().nullable().optional(),
  total: z.number().nullable().optional(),
  message: z.string(),
})

const envelope = <T extends z.ZodTypeAny>(item: T) =>
  z.object({
    case_id: z.string(),
    snapshot: z.string(),
    complete: z.boolean(),
    limits: z.array(LimitSchema),
    counts: z.record(z.string(), z.number()),
    items: z.array(item),
  })

export const DaySchema = z.object({
  day: z.string(),
  count: z.number(),
  offsets: z.string(),
  header: z.string(),
  zone_label: z.string(),
})
export type StreamDay = z.infer<typeof DaySchema>

export const StreamIndexSchema = envelope(DaySchema).extend({
  no_time_count: z.number(),
  no_time_position: z.enum(["first", "last"]),
  zone: z.object({ name: z.string(), label: z.string(), basis: z.string(), mode: z.string(), note: z.string().nullable() }),
  full_load_rows: z.number(),
  sort: z.string(),
  group_totals: z.object({ threads: z.number(), events: z.number() }).optional(),
})
export type StreamIndex = z.infer<typeof StreamIndexSchema>

export const StreamWindowSchema = envelope(StreamRowSchema)
export type StreamWindow = z.infer<typeof StreamWindowSchema>

export const PhoneSummarySchema = z.object({
  extraction_id: z.string(),
  label: z.string(),
  owner: ParticipantLabelSchema,
  device: z.object({
    manufacturer: z.string().nullable(),
    model: z.string().nullable(),
    os: z.string().nullable(),
    extraction_start: z.string().nullable().optional(),
  }),
  state: z.string(),
  standing: z.string(),
  ingest_progress: z.number().nullable(),
  device_zone: z.string().nullable(),
  device_zone_basis: z.string().nullable(),
  examiner_zone: z.string().nullable().optional(),
  report_version: z.string().nullable(),
  form: z.string().nullable(),
  report_filename: z.string().nullable(),
  ingested_at: z.string().nullable(),
  counts: z.object({
    messages: z.number(),
    calls: z.number(),
    emails: z.number(),
    locations: z.number(),
    files: z.number(),
    timeline_entries: z.number(),
  }),
})
export type PhoneSummary = z.infer<typeof PhoneSummarySchema>

export const PhonesSchema = z.object({
  case_id: z.string(),
  phones: z.array(PhoneSummarySchema),
  total: z.number(),
  case_zone: z.object({ name: z.string(), basis: z.string(), note: z.string().nullable() }),
})

const ValueSchema = z.object({
  index: z.number(),
  type: z.string().nullable(),
  text: z.string().nullable(),
  empty: z.boolean(),
  time: z
    .object({ original_text: z.string().nullable(), offset_present: z.boolean().nullable(), full: z.string(), instant: z.string().nullable() })
    .optional(),
})
export interface RecordFieldData {
  name: string | null
  kind: string
  data_type: string | null
  values: z.infer<typeof ValueSchema>[]
  attributes: Record<string, unknown>
  children: { record_uid: string; model_type: string; cellebrite_id: string | null; deleted_state: string | null; fields: RecordFieldData[] }[]
}
const FieldSchema: z.ZodType<RecordFieldData> = z.lazy(() =>
  z.object({
    name: z.string().nullable(),
    kind: z.string(),
    data_type: z.string().nullable(),
    values: z.array(ValueSchema),
    attributes: z.record(z.string(), z.unknown()),
    children: z.array(
      z.object({
        record_uid: z.string(),
        model_type: z.string(),
        cellebrite_id: z.string().nullable(),
        deleted_state: z.string().nullable(),
        fields: z.array(FieldSchema),
      }),
    ),
  }),
)

export const RecordDetailSchema = z.object({
  record_uid: z.string(),
  extraction: z.object({ id: z.string(), label: z.string(), report_filename: z.string().nullable(), report_sha256: z.string().nullable() }),
  model_type: z.string(),
  cellebrite_id: z.string().nullable(),
  title: z.string().nullable(),
  state: z.object({
    deleted_state: z.string().nullable(),
    is_carved: z.boolean(),
    decoding_confidence: z.string().nullable(),
    source_index: z.string().nullable(),
    interpretation_level: z.string().nullable(),
  }),
  fields: z.array(FieldSchema),
  times: z.array(
    z.object({
      record_uid: z.string(),
      field_path: z.string(),
      value_index: z.number(),
      instant: z.string().nullable(),
      full: z.string(),
      original_text: z.string(),
      offset_present: z.boolean(),
    }),
  ),
  files: z.array(
    z.object({
      record_uid: z.string(),
      file_uid: z.string().nullable(),
      mechanism: z.string(),
      reference: z.string().nullable(),
      path: z.string().nullable(),
      category: z.string().nullable(),
      size: z.number().nullable(),
      verification: z.string().nullable(),
      badge: z.string().nullable(),
      absence: z.string().nullable(),
    }),
  ),
  files_absence: z.string().nullable(),
  source_row: z.object({ available: z.boolean(), reason: z.string() }),
  corrections: z.array(
    z.object({
      field_path: z.string(),
      value_index: z.number(),
      original: z.string().nullable(),
      corrected: z.string().nullable(),
      current: z.boolean(),
      reason: z.string().nullable(),
      by: z.string().nullable(),
      at: z.string().nullable(),
    }),
  ),
  interpretation_level: z.string().nullable(),
  zone: z.string(),
  as_text: z.string(),
})
export type RecordDetail = z.infer<typeof RecordDetailSchema>
