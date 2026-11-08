import { z } from "zod"
import { fetchAPI } from "@/lib/api-client"
import { lazySchema } from "@/lib/lazy-schema"

const id = lazySchema(() => z.string().uuid())
const level = lazySchema(() =>
  z.enum(["strong", "moderate", "weak", "faint"]).nullable()
)

export const linkCandidate = lazySchema(() =>
  z
    .object({
      id,
      ref_id: z.string(),
      date: z.string().nullable(),
      dated: z.boolean(),
      direction: z.enum(["debit", "credit"]),
      amount_minor: z.string().regex(/^\d+$/),
      currency: z.string(),
      amount: z.string(),
      account_id: id,
      account_label: z.string(),
      from_name: z.string(),
      to_name: z.string(),
      description: z.string(),
      already_linked: z.boolean(),
    })
    .passthrough()
)
export type LinkPayment = z.infer<typeof linkCandidate>

const graded = lazySchema(() =>
  linkCandidate.extend({
    level,
    rule: z.string(),
    reasons: z.string(),
    gap_days: z.number().nullable(),
  })
)
export type LinkSuggestion = z.infer<typeof graded>

export const linkSuggestions = lazySchema(() =>
  z
    .object({
      case_id: id,
      mode: z.enum(["connected", "onward", "search", "named"]),
      anchor: linkCandidate.nullable(),
      rule: z.string(),
      compared: z.number(),
      total: z.number(),
      page: z.number(),
      page_size: z.number(),
      pages: z.number(),
      by_level: z.record(z.string(), z.number()),
      candidates: z.array(graded),
      elapsed_ms: z.number(),
      understood: z.string().optional(),
      not_found: z.number().optional(),
      left_out: z
        .object({
          words: z.string().nullable().optional(),
          common_words: z.string().nullable().optional(),
        })
        .passthrough()
        .optional(),
    })
    .passthrough()
)
export type LinkSuggestions = z.infer<typeof linkSuggestions>

async function read(caseId: string, url: string) {
  const result = linkSuggestions.parse(await fetchAPI(url))
  if (
    result.case_id !== caseId ||
    result.candidates.some((c) => !c.id) ||
    (result.anchor && !result.anchor.id)
  )
    throw Error("The suggestions belong to another case.")
  return result
}

export const linkSuggestionAPI = {
  suggestions: (
    caseId: string,
    transactionId: string,
    mode: "connected" | "onward",
    page = 1
  ) =>
    read(
      caseId,
      `/api/financial/payment-links/suggestions?${new URLSearchParams({
        case_id: caseId,
        transaction_id: transactionId,
        mode,
        page: String(page),
      })}`
    ),
  search: (
    caseId: string,
    q: string,
    opts: { transactionId?: string; direction?: string; page?: number } = {}
  ) => {
    const qs = new URLSearchParams({
      case_id: caseId,
      q,
      page: String(opts.page || 1),
    })
    if (opts.transactionId) qs.set("transaction_id", opts.transactionId)
    if (opts.direction) qs.set("direction", opts.direction)
    return read(caseId, `/api/financial/payment-links/search?${qs}`)
  },
  named: (caseId: string, transactionId: string, ids: string[]) => {
    const qs = new URLSearchParams({
      case_id: caseId,
      transaction_id: transactionId,
    })
    ids.forEach((i) => qs.append("ids", i))
    return read(caseId, `/api/financial/payment-links/named?${qs}`)
  },
}

/** Payment ids a model's answer cites, in order, once each: txn://<id> citations and the older Financial page links
 * (...&payment=<id>), the two forms lib/citations.ts reads as a ledger row. */
export function citedPaymentIds(answer: string): string[] {
  const uuid = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
  const found = [...answer.matchAll(new RegExp(`(?:txn://|payment=)(${uuid})`, "gi"))]
  return [...new Set(found.map((m) => m[1].toLowerCase()))]
}

export const LEVEL_WORDS: Record<string, string> = {
  strong: "Strong",
  moderate: "Moderate",
  weak: "Weak",
  faint: "Faint",
}
