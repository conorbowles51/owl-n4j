import { z } from "zod"

export const readerReplacementSchema = z.object({
  status: z.enum(["replaced", "restored"]),
  message: z.string(),
  counting_source_document_id: z.string(),
  replacement_source_document_id: z.string(),
  replaced_source_document_id: z.string(),
  investigator_work: z.boolean().default(false),
  can_restore: z.boolean().default(true),
})

export type ReaderReplacement = z.infer<typeof readerReplacementSchema>
