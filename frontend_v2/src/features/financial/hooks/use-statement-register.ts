import { useQuery } from "@tanstack/react-query"
import { z } from "zod"
import { fetchAPI } from "@/lib/api-client"
export const statementFile = z.object({
  id: z.string(),
  case_id: z.string(),
  original_filename: z.string(),
  status: z.string(),
  created_at: z.string().optional(),
  statement_root_evidence_id: z.string().nullable().optional(),
  statement_parent_evidence_id: z.string().nullable().optional(),
  financial_removed: z.boolean().default(false),
  financial_imports_removed: z.boolean().optional(),
  financial_visibility_revision: z.string().default("initial"),
})
export type StatementFile = z.infer<typeof statementFile>

export function groupStatementReadings(files: StatementFile[]) {
  const groups = new Map<string, StatementFile[]>()
  for (const file of files) {
    const key = file.statement_root_evidence_id || file.id
    groups.set(key, [...(groups.get(key) || []), file])
  }
  return [...groups.values()].map((versions) => {
    const byId = new Map(versions.map((file) => [file.id, file]))
    const depth = (file: StatementFile) => {
      const seen = new Set<string>()
      while (
        file.statement_parent_evidence_id &&
        byId.has(file.statement_parent_evidence_id) &&
        !seen.has(file.statement_parent_evidence_id)
      ) {
        seen.add(file.statement_parent_evidence_id)
        file = byId.get(file.statement_parent_evidence_id)!
      }
      return seen.size
    }
    const active = versions.filter((file) => !file.financial_removed)
    const current = [...(active.length ? active : versions)].sort(
      (a, b) =>
        (b.created_at || "").localeCompare(a.created_at || "") ||
        depth(b) - depth(a) ||
        b.id.localeCompare(a.id)
    )[0]
    return { ...current, readingVersions: versions }
  })
}
const listing = z.object({
  files: z.array(statementFile),
})
const importStates = z.object({
  case_id: z.string(),
  truncated: z.boolean(),
  files: z.array(
    z.object({
      evidence_file_id: z.string(),
      current_transactions: z.number().int().nonnegative(),
      incomplete_count: z.number().int().nonnegative().default(0),
      receipt_review_count: z.number().int().nonnegative().default(0),
      wire_review_count: z.number().int().nonnegative().default(0),
      prepared_periods: z.number().int().nonnegative().optional(),
      available_periods: z.number().int().nonnegative().default(0),
      pending_periods: z.number().int().nonnegative().default(0),
      periods_with_checks: z.number().int().nonnegative().default(0),
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

export function useStatementFiles(
  caseId: string | undefined,
  uploading = false,
  queuedIds: string[] = [],
  includeRemoved = false,
  enabled = true
) {
  return useQuery({
    enabled: enabled && !!caseId,
    select: (files) =>
      includeRemoved ? files : files.filter((file) => !file.financial_removed),
    queryKey: ["statement-import-files", caseId],
    queryFn: async () => {
      const result = listing.parse(
        await fetchAPI(
          `/api/evidence?${new URLSearchParams({ case_id: caseId!, include_reading_versions: "true" })}`
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
}

export function useStatementRegister(
  caseId: string,
  uploading = false,
  queuedIds: string[] = [],
  includeRemoved = false
) {
  const files = useStatementFiles(caseId, uploading, queuedIds, includeRemoved)
  const imports = useQuery({
    queryKey: ["statement-import-status", caseId],
    refetchInterval: 5000,
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
  const grouped = files.data ? groupStatementReadings(files.data) : undefined
  const saved =
    imports.data && grouped
      ? {
          ...imports.data,
          files: grouped.flatMap((file) => {
            const ids = new Set(
              file.readingVersions.map((version) => version.id)
            )
            const entries = imports.data.files.filter((item) =>
              ids.has(item.evidence_file_id)
            )
            if (!entries.length) return []
            const latest = entries.find(
              (entry) => entry.evidence_file_id === file.id
            )
            return [
              {
                evidence_file_id: file.id,
                current_transactions: entries.reduce(
                  (sum, entry) => sum + entry.current_transactions,
                  0
                ),
                incomplete_count: entries.reduce(
                  (sum, entry) => sum + entry.incomplete_count,
                  0
                ),
                receipt_review_count: entries.reduce(
                  (sum, entry) => sum + entry.receipt_review_count,
                  0
                ),
                wire_review_count: entries.reduce(
                  (sum, entry) => sum + entry.wire_review_count,
                  0
                ),
                periods: entries
                  .flatMap((entry) => entry.periods)
                  .filter((period) => period.source_status === "admitted"),
                history_periods: entries
                  .flatMap((entry) => entry.periods)
                  .filter((period) => period.source_status !== "admitted")
                  .length,
                prepared_periods: latest?.prepared_periods,
                available_periods: latest?.available_periods || 0,
                pending_periods: latest?.pending_periods || 0,
                periods_with_checks: latest?.periods_with_checks || 0,
              },
            ]
          }),
        }
      : imports.data
  return {
    files: { ...files, data: grouped },
    imports: { ...imports, data: saved },
  }
}
