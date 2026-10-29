import { z } from "zod"
import { fetchAPI } from "@/lib/api-client"

/** A saved statement Claude saved or entered for a person, and whether a person has confirmed it. */
export const statementModelWork = z.object({
  status: z.enum(["not_confirmed", "confirmed", "corrected"]),
  model: z.string(),
  for_person: z.string().nullable().optional(),
  confirmed_by: z.string().nullable().optional(),
  confirmed_at: z.string().nullable().optional(),
  calls: z.array(
    z.object({
      id: z.string(),
      rule_id: z.string(),
      status: z.string(),
      summary: z.string(),
      resolved_by: z.string().nullable().optional(),
    })
  ),
})
export type StatementModelWork = z.infer<typeof statementModelWork>

export async function confirmStatement(caseId: string, sourceDocumentId: string) {
  return statementModelWork.parse(
    await fetchAPI(
      `/api/financial/judgements/statements/${encodeURIComponent(sourceDocumentId)}/confirm?${new URLSearchParams({ case_id: caseId })}`,
      { method: "POST", body: {} }
    )
  )
}
