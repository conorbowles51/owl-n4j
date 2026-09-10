import { z } from "zod"
const minor = z.string().regex(/^-?(0|[1-9][0-9]*)$/)
export const printedTotalChecks = z
  .object({
    limitation: z.string(),
    checks: z
      .array(
        z
          .object({
            role: z.enum(["credits_total", "debits_total"]),
            status: z.enum(["balanced", "unbalanced", "unavailable"]),
            printed_minor: minor.nullable(),
            current_minor: minor,
            difference_minor: minor.nullable(),
            source: z
              .object({
                role: z.string(),
                original_text: z.string(),
                reviewed_value: z.string(),
                locator: z.unknown(),
              })
              .nullable(),
          })
          .refine((c) =>
            c.status === "unavailable"
              ? c.printed_minor === null &&
                c.difference_minor === null &&
                c.source === null
              : c.printed_minor !== null &&
                c.difference_minor !== null &&
                c.source !== null &&
                c.source.role === c.role &&
                c.source.reviewed_value === c.printed_minor &&
                BigInt(c.current_minor) - BigInt(c.printed_minor) ===
                  BigInt(c.difference_minor) &&
                (c.status === "balanced") ===
                  (BigInt(c.difference_minor) === 0n)
          )
      )
      .length(2),
  })
  .refine((v) => new Set(v.checks.map((c) => c.role)).size === 2)
export const printedTotalComparison = z.object({
  current: printedTotalChecks,
  proposed: printedTotalChecks,
})
