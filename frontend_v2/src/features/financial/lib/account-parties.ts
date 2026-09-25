import { z } from "zod"
const party = z.object({ id: z.string().uuid(), name: z.string().min(1) })
export const accountRelationship = z.object({
  id: z.string().uuid(),
  party,
  role: z.enum(["holder", "controller", "signatory", "analysis_group"]),
  basis: z.enum(["source", "investigator_knowledge"]),
  sources: z.array(
    z.object({
      source_document_id: z.string().uuid(),
      page_number: z.number().int().positive(),
    })
  ),
  effective_from: z.string().nullable(),
  effective_to: z.string().nullable(),
})
export const accountParties = z.object({
  case_id: z.string().uuid(),
  revision: z.string().regex(/^[a-f0-9]{64}$/),
  accounts: z.array(
    z.object({
      id: z.string().uuid(),
      canonical_id: z.string().uuid().optional(),
      holder_as_recorded: z.string().nullable(),
      identifier_as_printed: z.string().nullable(),
      institution: z.string().nullable(),
      currency: z.string().nullable(),
      account_type: z.string().nullable().optional(),
      statement_periods: z
        .array(
          z.object({
            id: z.string().uuid(),
            source_document_id: z.string().uuid(),
            start: z.string().nullable(),
            end: z.string().nullable(),
          })
        )
        .optional(),
      party: party.nullable(),
      relationships: z.array(accountRelationship).default([]),
      holder_parties: z.array(party).default([]),
    })
  ),
  parties: z.array(party),
  source_choices: z
    .array(
      z.object({
        source_document_id: z.string().uuid(),
        evidence_file_id: z.string().uuid().nullable(),
        account_id: z.string().uuid().nullable(),
        pages: z.array(z.number().int().positive()),
        label: z.string(),
      })
    )
    .default([]),
  ownership_review: z
    .object({
      suggestions: z.array(
        z.object({
          id: z.string(),
          scheme: z.string(),
          value: z.string(),
          account_ids: z.array(z.string().uuid()),
          suggested_name: z.string(),
          existing_party_id: z.string().uuid().nullable(),
          has_conflicting_links: z.boolean(),
          reason: z.string(),
          evidence: z.array(
            z.object({
              account_id: z.string().uuid(),
              source_document_id: z.string().uuid(),
              evidence_file_id: z.string().uuid().nullable(),
              page_number: z.number().int().positive(),
              printed_label: z.string(),
              printed_value: z.string(),
              holder_as_recorded: z.string(),
            })
          ),
        })
      ),
      conflicts: z.array(
        z.object({ account_id: z.string().uuid(), reason: z.string() })
      ),
    })
    .optional(),
  history: z.array(
    z.object({
      id: z.string().uuid(),
      account_id: z.string().uuid(),
      sequence: z.number().int().positive(),
      before: z.object({
        party: party.nullable(),
        relationships: z.array(accountRelationship).optional(),
      }),
      after: z.object({
        party: party.nullable(),
        relationships: z.array(accountRelationship).optional(),
      }),
      reason: z.string(),
      actor: z.string(),
      recorded_at: z.string(),
    })
  ),
  applied: z.boolean(),
  limitation: z.string(),
})
export type AccountParties = z.infer<typeof accountParties>
