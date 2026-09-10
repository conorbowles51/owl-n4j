import { z } from "zod"
const party = z.object({ id: z.string().uuid(), name: z.string().min(1) })
export const accountParties = z.object({
  case_id: z.string().uuid(),
  revision: z.string().regex(/^[a-f0-9]{64}$/),
  accounts: z.array(
    z.object({
      id: z.string().uuid(),
      holder_as_recorded: z.string().nullable(),
      identifier_as_printed: z.string().nullable(),
      institution: z.string().nullable(),
      currency: z.string().nullable(),
      party: party.nullable(),
    })
  ),
  parties: z.array(party),
  history: z.array(
    z.object({
      id: z.string().uuid(),
      account_id: z.string().uuid(),
      sequence: z.number().int().positive(),
      before: z.object({ party: party.nullable() }),
      after: z.object({ party: party.nullable() }),
      reason: z.string(),
      actor: z.string(),
      recorded_at: z.string(),
    })
  ),
  applied: z.boolean(),
  limitation: z.string(),
})
export type AccountParties = z.infer<typeof accountParties>
