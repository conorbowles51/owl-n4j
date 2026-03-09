import { FileText } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { useQuery } from "@tanstack/react-query"
import { workspaceAPI } from "../api"
import { WorkspaceSection } from "./WorkspaceSection"

interface DocumentsSectionProps {
  caseId: string
}

export function DocumentsSection({ caseId }: DocumentsSectionProps) {
  const { data: pinned = [] } = useQuery({
    queryKey: ["workspace", caseId, "pinned"],
    queryFn: () => workspaceAPI.getPinnedItems(caseId),
  })

  const documents = pinned.filter((p) => p.item_type === "document")

  return (
    <WorkspaceSection
      title="Linked Documents"
      icon={FileText}
      count={documents.length}
      defaultOpen={false}
    >
      <div className="space-y-1">
        {documents.map((doc) => (
          <div
            key={doc.id}
            className="flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-muted/30"
          >
            <FileText className="size-3 text-muted-foreground" />
            <span className="flex-1 truncate text-xs">{doc.item_id}</span>
            {doc.annotations_count !== undefined && doc.annotations_count > 0 && (
              <Badge variant="outline" className="text-[10px]">
                {doc.annotations_count} annotations
              </Badge>
            )}
          </div>
        ))}
        {documents.length === 0 && (
          <p className="py-3 text-center text-xs text-muted-foreground">
            No documents linked
          </p>
        )}
      </div>
    </WorkspaceSection>
  )
}
