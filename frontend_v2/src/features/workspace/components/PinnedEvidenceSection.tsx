import { useMemo } from "react"
import { Pin, FileText, Paperclip, PinOff } from "lucide-react"
import { useQuery } from "@tanstack/react-query"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { evidenceAPI } from "@/features/evidence/api"
import { usePinnedItems, useUnpinItem } from "../hooks/use-workspace"
import { formatWorkspaceDateTime } from "../lib/format-date"

interface PinnedEvidenceSectionProps {
  caseId: string
}

export function PinnedEvidenceSection({ caseId }: PinnedEvidenceSectionProps) {
  const { data: pinned = [] } = usePinnedItems(caseId)
  const unpinItem = useUnpinItem(caseId)
  const { data: evidenceFiles = [] } = useQuery({
    queryKey: ["workspace", caseId, "pinned-evidence-files"],
    queryFn: () => evidenceAPI.list(caseId),
  })

  const entries = useMemo(() => {
    const evidenceById = new Map(evidenceFiles.map((file) => [file.id, file]))
    return [...pinned]
      .map((item) => {
        const evidence = evidenceById.get(item.item_id)
        return {
          ...item,
          label: evidence?.original_filename || item.item_id,
          created_at: evidence?.created_at || item.created_at,
        }
      })
      .sort((a, b) => {
        const aTime = a.created_at ? new Date(a.created_at).getTime() : 0
        const bTime = b.created_at ? new Date(b.created_at).getTime() : 0
        return bTime - aTime
      })
  }, [evidenceFiles, pinned])

  return (
    <div className="rounded-lg border border-border p-4">
      <div className="mb-3 flex items-center gap-2">
        <Pin className="size-4 text-amber-500" />
        <h3 className="text-xs font-semibold">Pinned Evidence</h3>
        <Badge variant="slate" className="h-4 px-1.5 text-[10px]">
          {entries.length}
        </Badge>
      </div>

      {entries.length === 0 ? (
        <div className="rounded-md border border-dashed border-border py-6 text-center text-xs text-muted-foreground">
          No pinned evidence yet. Pin items from Documents or Case Files to keep them handy.
        </div>
      ) : (
        <div className="space-y-2">
          {entries.map((item) => {
            const icon = item.item_type === "document" ? FileText : Paperclip
            const Icon = icon
            return (
              <div
                key={item.id}
                className="flex items-center gap-2 rounded-md border border-border/60 px-3 py-2"
              >
                <Icon className="size-3.5 text-muted-foreground" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-medium">{item.label}</p>
                  {item.created_at && (
                    <p className="text-[10px] text-muted-foreground">
                      {formatWorkspaceDateTime(item.created_at)}
                    </p>
                  )}
                </div>
                <Badge variant="outline" className="text-[10px] uppercase">
                  {item.item_type}
                </Badge>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  onClick={() => unpinItem.mutate(item.id)}
                  aria-label={`Unpin ${item.label}`}
                >
                  <PinOff className="size-3.5" />
                </Button>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
