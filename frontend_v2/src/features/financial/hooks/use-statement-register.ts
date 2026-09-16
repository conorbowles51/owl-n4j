import { useQuery } from "@tanstack/react-query"
import { z } from "zod"
import { fetchAPI } from "@/lib/api-client"
const listing = z.object({
  files: z.array(
    z.object({
      id: z.string(),
      case_id: z.string(),
      original_filename: z.string(),
      status: z.string(),
      created_at: z.string().optional(),
    })
  ),
})
const importStates = z.object({
  case_id: z.string(),
  truncated: z.boolean(),
  files: z.array(
    z.object({
      evidence_file_id: z.string(),
      current_transactions: z.number().int().nonnegative(),
      receipt_review_count: z.number().int().nonnegative().default(0),
      wire_review_count: z.number().int().nonnegative().default(0),
      periods: z.array(
        z.object({
          id: z.string(),
          account_id: z.string(),
          account_label: z.string(),
          start: z.string().nullable(),
          end: z.string().nullable(),
          source_status: z.string(),
        })
      ),
    })
  ),
})

export function useStatementRegister(
  caseId: string,
  uploading = false,
  queuedIds: string[] = []
) {
  const files = useQuery({
    queryKey: ["statement-import-files", caseId],
    queryFn: async () => {
      const result = listing.parse(
        await fetchAPI(
          `/api/evidence?${new URLSearchParams({ case_id: caseId })}`
        )
      )
      if (result.files.some((file) => file.case_id !== caseId))
        throw Error("The returned file list belongs to another case.")
      return result.files.filter((file) =>
        file.original_filename.toLowerCase().endsWith(".pdf")
      )
    },
    refetchInterval: (query) =>
      uploading ||
      query.state.data?.some(
        (file) =>
          ["processing", "queued"].includes(file.status) ||
          (file.status === "unprocessed" && queuedIds.includes(file.id))
      )
        ? 3000
        : false,
  })
  const imports = useQuery({
    queryKey: ["statement-import-status", caseId],
    queryFn: async () => {
      const result = importStates.parse(
        await fetchAPI(
          `/api/financial/statement-import/files?${new URLSearchParams({ case_id: caseId })}`
        )
      )
      if (result.case_id !== caseId)
        throw Error("The import status belongs to another case.")
      return result
    },
  })
  return { files, imports }
}
