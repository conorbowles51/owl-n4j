import { useState } from "react"
import type { ComponentType } from "react"
import {
  ChartColumn,
  Download,
  FileText,
  GitBranch,
  Loader2,
  Map as MapIcon,
  Save,
  Table2,
} from "lucide-react"
import { useQuery } from "@tanstack/react-query"
import { toast } from "sonner"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { agentAPI, type AgentArtifactExportFormat } from "@/features/agent/api"
import type { AgentArtifactType, SavedAgentArtifact } from "@/features/agent/types"
import { downloadProtectedFile } from "@/lib/protected-file"
import { formatWorkspaceDateTime } from "../lib/format-date"

interface SavedArtifactsSectionProps {
  caseId: string
}

const artifactIcons: Record<AgentArtifactType, ComponentType<{ className?: string }>> = {
  graph: GitBranch,
  table: Table2,
  map: MapIcon,
  report: FileText,
  chart: ChartColumn,
}

export function SavedArtifactsSection({ caseId }: SavedArtifactsSectionProps) {
  const [activeDownload, setActiveDownload] = useState<string | null>(null)
  const { data: artifacts = [] } = useQuery({
    queryKey: ["agent", "saved", caseId],
    queryFn: () => agentAPI.listSavedArtifacts(caseId),
  })

  const downloadArtifact = async (
    artifact: SavedAgentArtifact,
    format: AgentArtifactExportFormat,
  ) => {
    const key = `${artifact.id}:${format}`
    if (activeDownload) return
    setActiveDownload(key)
    try {
      await downloadProtectedFile(
        agentAPI.savedArtifactExportUrl(artifact.id, format),
        savedArtifactFilename(artifact, format),
      )
      toast.success(`${format.toUpperCase()} export downloaded`)
    } catch (error) {
      const message = error instanceof Error ? error.message : `Failed to download ${format.toUpperCase()}`
      toast.error(message)
    } finally {
      setActiveDownload(null)
    }
  }

  return (
    <div className="rounded-lg border border-border p-4">
      <div className="mb-3 flex items-center gap-2">
        <Save className="size-4 text-emerald-600" />
        <h3 className="text-xs font-semibold">Saved Artifacts</h3>
        <Badge variant="slate" className="h-4 px-1.5 text-[10px]">
          {artifacts.length}
        </Badge>
      </div>

      {artifacts.length === 0 ? (
        <div className="rounded-md border border-dashed border-border py-6 text-center text-xs text-muted-foreground">
          No saved artifacts yet.
        </div>
      ) : (
        <div className="space-y-2">
          {artifacts.map((artifact) => {
            const Icon = artifactIcons[artifact.artifact_type] ?? FileText
            const formats: AgentArtifactExportFormat[] =
              artifact.artifact_type === "report" ? ["pdf", "docx"] : ["csv"]
            const modelId = modelFromProvenance(artifact)
            return (
              <div
                key={artifact.id}
                className="flex items-center gap-2 rounded-md border border-border/60 px-3 py-2"
              >
                <Icon className="size-3.5 shrink-0 text-muted-foreground" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-medium">{artifact.title}</p>
                  <p className="truncate text-[10px] text-muted-foreground">
                    {formatWorkspaceDateTime(artifact.created_at)}
                    {modelId ? ` - ${modelId}` : ""}
                  </p>
                  {artifact.note && (
                    <p className="mt-0.5 line-clamp-2 text-[10px] text-muted-foreground">
                      {artifact.note}
                    </p>
                  )}
                </div>
                <Badge variant="outline" className="text-[10px] uppercase">
                  {artifact.destination}
                </Badge>
                <Badge variant="secondary" className="text-[10px] capitalize">
                  {artifact.artifact_type}
                </Badge>
                <div className="flex shrink-0 items-center gap-1">
                  {formats.map((format) => {
                    const key = `${artifact.id}:${format}`
                    return (
                      <Button
                        key={format}
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="h-7 px-2 text-xs"
                        onClick={() => downloadArtifact(artifact, format)}
                        disabled={activeDownload !== null}
                        title={`Download ${format.toUpperCase()}`}
                      >
                        {activeDownload === key ? (
                          <Loader2 className="mr-1 size-3 animate-spin" />
                        ) : (
                          <Download className="mr-1 size-3" />
                        )}
                        {format === "docx" ? "Word" : format.toUpperCase()}
                      </Button>
                    )
                  })}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

function modelFromProvenance(artifact: SavedAgentArtifact): string | null {
  const run = artifact.provenance["run"]
  if (!run || typeof run !== "object") return null
  const modelId = (run as Record<string, unknown>).model_id
  return typeof modelId === "string" && modelId.trim() ? modelId : null
}

function savedArtifactFilename(
  artifact: SavedAgentArtifact,
  format: AgentArtifactExportFormat,
) {
  const slug = artifact.title
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "")
  return `${slug || "saved-artifact"}-${artifact.artifact_type}.${format}`
}
