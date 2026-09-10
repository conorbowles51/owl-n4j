import { z } from "zod"
export const postingGraph = z
  .object({
    case_id: z.string(),
    account_id: z.string().nullable(),
    start_date: z.string().nullable(),
    end_date: z.string().nullable(),
    population: z.enum(["working", "verified"]),
    snapshot_sha256: z.string().regex(/^[a-f0-9]{64}$/),
    applied: z.literal(false),
    limitation: z.string(),
    excluded_rows: z.number().int().nonnegative(),
    nodes: z
      .array(
        z.object({
          id: z.string(),
          kind: z.enum(["account", "source_label"]),
          account_id: z.string(),
          label: z.string(),
        })
      )
      .max(2000),
    edges: z
      .array(
        z.object({
          id: z.string(),
          source: z.string(),
          target: z.string(),
          transaction_id: z.string(),
          source_document_id: z.string(),
          currency: z.string(),
          amount_minor: z.string().regex(/^(0|[1-9][0-9]*)$/),
          direction: z.enum(["credit", "debit"]),
          ordering_date: z.string(),
          description: z.string().nullable(),
          proof_class: z.enum(["p0", "p1", "p2", "p3"]),
        })
      )
      .max(1000),
  })
  .superRefine((data, ctx) => {
    const nodes = new Map(data.nodes.map((n) => [n.id, n]))
    const ids = new Set<string>()
    if (nodes.size !== data.nodes.length)
      ctx.addIssue({ code: "custom", message: "Repeated graph node." })
    for (const edge of data.edges) {
      const a = nodes.get(edge.source),
        b = nodes.get(edge.target)
      if (
        !a ||
        !b ||
        a.account_id !== b.account_id ||
        edge.id !== edge.transaction_id ||
        ids.has(edge.id) ||
        (edge.direction === "debit"
          ? a.kind !== "account" || b.kind !== "source_label"
          : a.kind !== "source_label" || b.kind !== "account")
      )
        ctx.addIssue({
          code: "custom",
          message: "Graph edge does not match its account and source group.",
        })
      ids.add(edge.id)
    }
  })
export type PostingGraph = z.infer<typeof postingGraph>
