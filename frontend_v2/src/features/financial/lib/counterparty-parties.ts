import { z } from "zod"
const party = z.object({ id: z.string().uuid(), name: z.string().min(1) })
export const counterpartyParties = z
  .object({
    case_id: z.string().uuid(),
    revision: z.string().regex(/^[a-f0-9]{64}$/),
    applied: z.boolean(),
    limitation: z.string(),
    parties: z.array(party),
    event_ids: z.array(z.string().uuid()).optional(),
    readings: z
      .array(
        z.object({
          transaction_id: z.string().uuid(),
          ref_id: z.string(),
          account_id: z.string().uuid(),
          currency: z.string(),
          counterparty_raw: z.string().nullable(),
          description: z.string().nullable(),
          amount_minor: z.string().regex(/^(0|[1-9][0-9]*)$/),
          direction: z.enum(["credit", "debit"]),
          party: party.nullable(),
          decision_transaction_id: z.string().uuid().nullable(),
        })
      )
      .max(5000),
    history: z
      .array(
        z.object({
          id: z.string().uuid(),
          transaction_id: z.string().uuid(),
          sequence: z.number().int().positive(),
          before: z.object({ party: party.nullable(), override: z.boolean() }),
          after: z.object({
            party: party.nullable(),
            override: z.literal(true),
          }),
          reason: z.string(),
          actor: z.string().nullable(),
          recorded_at: z.string(),
        })
      )
      .max(10000),
  })
  .superRefine((value, ctx) => {
    const parties = new Map(value.parties.map((p) => [p.id, p.name]))
    if (
      parties.size !== value.parties.length ||
      new Set(value.readings.map((r) => r.transaction_id)).size !==
        value.readings.length ||
      value.readings.some(
        (r) => r.party && parties.get(r.party.id) !== r.party.name
      )
    )
      ctx.addIssue({
        code: "custom",
        message: "Counterparty identity scope is inconsistent.",
      })
  })
