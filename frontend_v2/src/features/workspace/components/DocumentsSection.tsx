import { FileText } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { usePinnedItems } from "../hooks/use-workspace"

interface DocumentsSectionProps {
  caseId: string
}

export function DocumentsSection({ caseId }: DocumentsSectionProps) {
  const { data: pinned = [] } = usePinnedItems(caseId)
  const documents = pinned.filter((p) => p.item_type === "document")

  if (documents.length === 0) return null

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <FileText className="size-3.5 text-muted-foreground" />
        <h3 className="text-xs font-semibold">Linked Documents</h3>
        <Badge variant="slate" className="h-4 px-1.5 text-[10px]">
          {documents.length}
        </Badge>
      </div>
      <div className="space-y-1">
        {documents.map((doc) => (
          <div
            key={doc.id}
            className="flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-muted/30"
          >
            <FileText className="size-3 text-muted-foreground" />
            <span className="flex-1 truncate text-xs">{doc.item_id}</span>
            {doc.annotations_count != null && doc.annotations_count > 0 && (
              <Badge variant="outline" className="text-[10px]">
                {doc.annotations_count} annotations
              </Badge>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
