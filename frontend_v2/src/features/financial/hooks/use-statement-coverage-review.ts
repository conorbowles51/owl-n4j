import { useEffect, useState } from "react"
import { z } from "zod"
import { fetchAPI } from "@/lib/api-client"

export const coverageReview = z.object({
  available: z.boolean(),
  revision: z.string().nullable(),
  reason: z.string().optional(),
  matching_statement: z.boolean().optional(),
  candidates: z.array(
    z.object({
      file_id: z.string(),
      statement_id: z.string().nullish(),
      source_document_id: z.string().nullish(),
      filename: z.string(),
      page_number: z.number().int().positive().optional(),
      status: z.enum(["imported", "awaiting_import"]),
      period_start: z.string(),
      period_end: z.string(),
      matching_statement: z.boolean().optional(),
    })
  ),
})
export type CoverageReview = z.infer<typeof coverageReview>
export function useStatementCoverageReview(
  caseId: string,
  fileId: string,
  request: {
    expected_revision: string
    statement_id: string | null
    replaces_source_document_id?: string
    currency: string
    institution: string
    account_number: string
    holder?: string
    period_start: string
    period_end: string
  },
  enabled = true
) {
  const payload = JSON.stringify(request),
    key = `${caseId}:${fileId}:${payload}`
  const [attempt, setAttempt] = useState(0)
  const [result, setResult] = useState<{
    key: string
    data?: CoverageReview
    error?: string
  }>()
  useEffect(() => {
    if (!enabled) return
    const controller = new AbortController()
    const timer = window.setTimeout(async () => {
      try {
        const raw = await fetchAPI(
          `/api/financial/statement-import/${fileId}/coverage-check?case_id=${caseId}`,
          {
            method: "POST",
            body: JSON.parse(payload),
            signal: controller.signal,
          }
        )
        const value = z
          .object({
            case_id: z.literal(caseId),
            evidence_file_id: z.literal(fileId),
          })
          .extend(coverageReview.shape)
          .parse(raw)
        if (!controller.signal.aborted) setResult({ key, data: value })
      } catch (error) {
        if (!controller.signal.aborted)
          setResult({
            key,
            error:
              error instanceof Error
                ? error.message
                : "The other statement dates could not be checked.",
          })
      }
    }, 350)
    return () => {
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [caseId, fileId, payload, key, enabled, attempt])
  const current = enabled && result?.key === key ? result : undefined
  return {
    data: current?.data,
    error: current?.error,
    pending: enabled && !current,
    retry: () => {
      setResult(undefined)
      setAttempt((x) => x + 1)
    },
  }
}
