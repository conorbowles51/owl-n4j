import { useMemo } from "react"
import { useQuery } from "@tanstack/react-query"
import { FileText, Pin, PinOff } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { evidenceAPI } from "@/features/evidence/api"
import { usePinItem, usePinnedItems, useUnpinItem } from "../hooks/use-workspace"
import { formatWorkspaceDateTime } from "../lib/format-date"

interface DocumentsSectionProps {
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

export function DocumentsSection({ caseId }: DocumentsSectionProps) {
  const { data: evidenceFiles = [] } = useQuery({
    queryKey: ["workspace", caseId, "documents"],
    queryFn: () => evidenceAPI.list(caseId),
  })
  const { data: pinned = [] } = usePinnedItems(caseId)
  const pinItem = usePinItem(caseId)
  const unpinItem = useUnpinItem(caseId)

  const documents = useMemo(
    () => evidenceFiles.filter((file) => isDocumentFile(file.original_filename || "")),
    [evidenceFiles],
  )

  return (
    <div className="rounded-lg border border-border p-4">
      <div className="mb-3 flex items-center gap-2">
        <FileText className="size-4 text-emerald-500" />
        <h3 className="text-xs font-semibold">Documents</h3>
        <Badge variant="slate" className="h-4 px-1.5 text-[10px]">
          {documents.length}
        </Badge>
      </div>

      {documents.length === 0 ? (
        <div className="rounded-md border border-dashed border-border py-6 text-center text-xs text-muted-foreground">
          No supplementary documents yet.
        </div>
      ) : (
        <div className="space-y-2">
          {documents.slice(0, 8).map((doc) => {
            const pinnedEntry = pinned.find((item) => item.item_id === doc.id)
            return (
              <div
                key={doc.id}
                className="flex items-center gap-3 rounded-md border border-border/60 px-3 py-2"
              >
                <FileText className="size-3.5 text-muted-foreground" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-medium">{doc.original_filename}</p>
                  <p className="text-[10px] text-muted-foreground">
                    {formatWorkspaceDateTime(doc.created_at)}
                  </p>
                </div>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  onClick={() =>
                    pinnedEntry
                      ? unpinItem.mutate(pinnedEntry.id)
                      : pinItem.mutate({ itemType: "document", itemId: doc.id })
                  }
                >
                  {pinnedEntry ? <PinOff className="size-3.5" /> : <Pin className="size-3.5" />}
                </Button>
              </div>
            )
          })}
          {documents.length > 8 && (
            <p className="text-[10px] text-muted-foreground">
              +{documents.length - 8} more documents in this case
            </p>
          )}
        </div>
      )}
    </div>
  )
}
