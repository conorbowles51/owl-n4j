import { useMemo } from "react"
import { useQuery } from "@tanstack/react-query"
import { Paperclip, Pin, PinOff } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { evidenceAPI } from "@/features/evidence/api"
import { usePinItem, usePinnedItems, useUnpinItem } from "../hooks/use-workspace"
import { formatWorkspaceDateTime } from "../lib/format-date"

interface CaseFilesSectionProps {
  caseId: string
}

function isDocumentFile(filename: string) {
  const lower = filename.toLowerCase()
  if (lower.startsWith("note_") && lower.endsWith(".txt")) return true
  if (lower.startsWith("link_") || lower.endsWith("_link.txt")) return true
  const imageExtensions = [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg"]
  if (imageExtensions.some((ext) => lower.endsWith(ext))) return true
  const docExtensions = [".pdf", ".doc", ".docx", ".txt", ".rtf"]
  if (docExtensions.some((ext) => lower.endsWith(ext))) {
    const isSimpleName = lower.split(".").length === 2
    const hasQuickActionPattern = lower.startsWith("note_") || lower.startsWith("link_")
    return isSimpleName || hasQuickActionPattern
  }
  return false
}

export function CaseFilesSection({ caseId }: CaseFilesSectionProps) {
  const { data: evidenceFiles = [] } = useQuery({
    queryKey: ["workspace", caseId, "case-files"],
    queryFn: () => evidenceAPI.list(caseId),
  })
  const { data: pinned = [] } = usePinnedItems(caseId)
  const pinItem = usePinItem(caseId)
  const unpinItem = useUnpinItem(caseId)

  const caseFiles = useMemo(
    () => evidenceFiles.filter((file) => !isDocumentFile(file.original_filename || "")),
    [evidenceFiles],
  )

  return (
    <div className="rounded-lg border border-border p-4">
      <div className="mb-3 flex items-center gap-2">
        <Paperclip className="size-4 text-slate-500" />
        <h3 className="text-xs font-semibold">Case Files</h3>
        <Badge variant="slate" className="h-4 px-1.5 text-[10px]">
          {caseFiles.length}
        </Badge>
      </div>

      {caseFiles.length === 0 ? (
        <p className="text-xs text-muted-foreground">No case files uploaded yet.</p>
      ) : (
        <div className="space-y-2">
          {caseFiles.slice(0, 8).map((file) => {
            const pinnedEntry = pinned.find((item) => item.item_id === file.id)
            return (
              <div
                key={file.id}
                className="flex items-center gap-3 rounded-md border border-border/60 px-3 py-2"
              >
                <Paperclip className="size-3.5 text-muted-foreground" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-medium">{file.original_filename}</p>
                  <p className="text-[10px] text-muted-foreground">
                    {formatWorkspaceDateTime(file.created_at)}
                  </p>
                </div>
                <Badge variant="outline" className="text-[10px]">
                  {file.status}
                </Badge>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  onClick={() =>
                    pinnedEntry
                      ? unpinItem.mutate(pinnedEntry.id)
                      : pinItem.mutate({ itemType: "evidence", itemId: file.id })
                  }
                >
                  {pinnedEntry ? <PinOff className="size-3.5" /> : <Pin className="size-3.5" />}
                </Button>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
