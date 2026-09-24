import { useEffect, useState } from "react"
import { z } from "zod"
import { fetchAPI } from "@/lib/api-client"

const finding = z.object({
  row_id: z.string().nullish(),
  page: z.number().nullish(),
  expected_minor: z.string(),
  printed_minor: z.string(),
  difference_minor: z.string(),
})
export const arithmeticCheck = z.object({
  kind: z.enum([
    "closing_balance",
    "running_balance",
    "credit_total",
    "debit_total",
    "fee_total",
    "interest_total",
  ]),
  status: z.enum(["matches", "difference", "unavailable"]),
  reason: z.string().optional(),
  row_id: z.string().nullish(),
  contributing_row_ids: z.array(z.string()).optional(),
  expected_minor: z.string().optional(),
  printed_minor: z.string().optional(),
  difference_minor: z.string().optional(),
  compared_intervals: z.number().optional(),
  mismatch_count: z.number().optional(),
  findings: z.array(finding).optional(),
  findings_truncated: z.boolean().optional(),
})
const resultSchema = z.object({
  revision: z.string(),
  checks_revision: z.string(),
  applied: z.literal(false),
  checks: z.array(arithmeticCheck),
  admission: z
    .object({
      can_import: z.boolean(),
      status: z.string(),
      revision: z.string(),
      blockers: z.array(
        z.object({
          message: z.string(),
          row_id: z.string().nullish(),
          field: z.string().optional(),
          kind: z.string().optional(),
        })
      ),
    })
    .optional(),
})

// Associate every response with its exact edit snapshot. An old response must
// never enable confirmation after the investigator has changed another value.
export function useStatementChecks(
  caseId: string,
  fileId: string,
  request: {
    expected_revision: string
    statement_id: string | null
    currency: string
    holder?: string
    account_number?: string
    institution?: string
    period_start?: string
    period_end?: string
    no_activity_confirmed?: boolean
    no_activity_revision?: string | null
    rows: unknown[]
  }
) {
  const payload = JSON.stringify(request)
  const key = `${caseId}:${fileId}:${payload}`
  const [attempt, setAttempt] = useState(0)
  const [result, setResult] = useState<{
    key: string
    data?: z.infer<typeof resultSchema>
    error?: string
  }>()
  useEffect(() => {
    const controller = new AbortController()
    const timer = window.setTimeout(async () => {
      try {
        const body = JSON.parse(payload) as typeof request
        const data = resultSchema.parse(
          await fetchAPI(
            `/api/financial/statement-import/${fileId}/checks?${new URLSearchParams({ case_id: caseId })}`,
            { method: "POST", body, signal: controller.signal }
          )
        )
        if (data.revision !== body.expected_revision)
          throw Error("The statement reading changed. Reopen this review.")
        if (!controller.signal.aborted) setResult({ key, data })
      } catch (error) {
        if (!controller.signal.aborted)
          setResult({
            key,
            error:
              error instanceof Error
                ? error.message
                : "The statement checks could not finish.",
          })
      }
    }, 350)
    return () => {
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [caseId, fileId, payload, key, attempt])
  const current = result?.key === key ? result : undefined
  return {
    checks: current?.data?.checks ?? [],
    revision: current?.data?.checks_revision,
    admission: current?.data?.admission,
    pending: !current,
    error: current?.error,
    retry: () => {
      setResult(undefined)
      setAttempt((n) => n + 1)
    },
  }
}
