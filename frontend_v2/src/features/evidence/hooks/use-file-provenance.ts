import { useQuery } from "@tanstack/react-query"
import { z } from "zod"
import { fetchAPI } from "@/lib/api-client"

/**
 * Who uploaded each file, and who added it to Financial, when and from where.
 * Only what the system recorded: a person is never named when no record names
 * them (``added_by`` / ``uploaded_by`` stay null).
 */
const provenance = z.object({
  file_id: z.string(),
  uploaded_by: z.string().nullable(),
  uploaded_at: z.string().nullable(),
  uploaded_from: z.string().nullable(),
  in_financial: z.boolean(),
  added_by: z.string().nullable(),
  added_at: z.string().nullable(),
  added_automatically: z.boolean(),
  auto_reason: z.string().nullable(),
  added_from: z.string().nullable(),
  added_via: z.string().nullable(),
  batch_id: z.string().nullable(),
})
export type FileProvenance = z.infer<typeof provenance>

export const fileProvenanceKey = (caseId: string) => ["file-provenance", caseId]

export function useFileProvenance(caseId: string, fileIds: string[]) {
  const ids = [...new Set(fileIds)].sort()
  return useQuery({
    queryKey: [...fileProvenanceKey(caseId), ids],
    enabled: !!caseId && ids.length > 0,
    staleTime: 30_000,
    queryFn: async () =>
      z
        .object({ files: z.record(z.string(), provenance) })
        .parse(
          await fetchAPI(
            `/api/activity/files?case_id=${encodeURIComponent(caseId)}`,
            { method: "POST", body: { file_ids: ids } }
          )
        ).files,
  })
}

export function formatWhen(value: string | null) {
  if (!value) return ""
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString(undefined, {
        day: "numeric",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        timeZoneName: "short",
      })
}

/** "In Financial · added by Alex, 27 Oct 2026, 18:02 UTC", or null when the file is not in Financial. */
export function financialLine(item: FileProvenance | undefined) {
  if (!item?.in_financial) return null
  const when = formatWhen(item.added_at)
  if (item.added_automatically)
    return `In Financial · added automatically (${item.auto_reason || "statement detection"})${when ? `, ${when}` : ""}`
  if (item.added_by)
    return `In Financial · added by ${item.added_by}${when ? `, ${when}` : ""}`
  return `In Financial${when ? ` · since ${when}` : ""} · who added it was not recorded`
}

export function uploadLine(item: FileProvenance | undefined, createdAt: string | null) {
  const when = formatWhen(item?.uploaded_at ?? createdAt)
  if (item?.uploaded_by) return `Uploaded by ${item.uploaded_by}${when ? `, ${when}` : ""}`
  return `Uploaded ${when || "(date not recorded)"} · uploader not recorded`
}
