import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { AlertCircle } from "lucide-react"
import { evidenceAPI } from "../../api"
import { useQuery } from "@tanstack/react-query"
import { fetchAPI } from "@/lib/api-client"
import type { EvidenceFile } from "@/types/evidence.types"

interface TextPreviewProps {
  file: EvidenceFile
  caseId: string
}

function getRelativePath(file: EvidenceFile, caseId: string): string | undefined {
  let path = file.stored_path?.replace(/\\/g, "/")
  if (!path) return undefined
  path = path.replace(/^ingestion\/data\//, "")
  if (path.startsWith(`${caseId}/`)) {
    return path.substring(caseId.length + 1)
  }
  return path
}

/** Fetch text content via the evidence file proxy endpoint (for engine-managed files). */
function useEngineFileContent(evidenceId: string, enabled: boolean) {
  return useQuery({
    queryKey: ["evidence-file-content", evidenceId],
    queryFn: async () => {
      const url = evidenceAPI.getFileUrl(evidenceId)
      const resp = await fetch(url, { credentials: "include" })
      if (!resp.ok) throw new Error("Failed to fetch file")
      return resp.text()
    },
    enabled,
    staleTime: 60_000,
  })
}

export function TextPreview({ file, caseId }: TextPreviewProps) {
  const isEngineManagedFile = !!file.engine_job_id && !file.stored_path
  const relativePath = isEngineManagedFile ? undefined : getRelativePath(file, caseId)

  // Inline filesystem content query for legacy files
  const legacyQuery = useQuery({
    queryKey: ["filesystem-content", caseId, relativePath],
    queryFn: async () => {
      const qs = new URLSearchParams({ case_id: caseId, path: relativePath! })
      const res = await fetchAPI<{ content: string }>(`/api/filesystem/read?${qs}`)
      return res.content
    },
    enabled: !!relativePath && !isEngineManagedFile,
    staleTime: 60_000,
  })
  const engineQuery = useEngineFileContent(file.id, isEngineManagedFile)

  const { data: content, isLoading, error } = isEngineManagedFile ? engineQuery : legacyQuery

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <LoadingSpinner size="sm" />
        <span className="ml-2 text-xs text-muted-foreground">Loading file content...</span>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex items-start gap-2 rounded-md bg-red-50 dark:bg-red-500/10 p-3">
        <AlertCircle className="mt-0.5 size-4 text-red-600 dark:text-red-400" />
        <p className="text-xs text-muted-foreground">Could not load file preview</p>
      </div>
    )
  }

  const displayContent = typeof content === "string" && content.length > 50000
    ? content.substring(0, 50000) + "\n\n... (truncated)"
    : content

  return (
    <pre className="max-h-[500px] overflow-auto rounded-md bg-muted/50 p-3 font-mono text-xs leading-relaxed text-foreground whitespace-pre-wrap">
      {displayContent || "Empty file"}
    </pre>
  )
}
