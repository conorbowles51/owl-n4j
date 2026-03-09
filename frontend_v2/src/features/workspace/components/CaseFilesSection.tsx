import { Paperclip } from "lucide-react"
import { useQuery } from "@tanstack/react-query"
import { workspaceAPI } from "../api"
import { WorkspaceSection } from "./WorkspaceSection"

interface CaseFilesSectionProps {
  caseId: string
}

export function CaseFilesSection({ caseId }: CaseFilesSectionProps) {
  const { data: pinned = [] } = useQuery({
    queryKey: ["workspace", caseId, "pinned"],
    queryFn: () => workspaceAPI.getPinnedItems(caseId),
  })

  const files = pinned.filter((p) => p.item_type === "file")

  return (
    <WorkspaceSection
      title="Case Files"
      icon={Paperclip}
      count={files.length}
      defaultOpen={false}
    >
      <div className="space-y-1">
        {files.map((file) => (
          <div
            key={file.id}
            className="flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-muted/30"
          >
            <Paperclip className="size-3 text-muted-foreground" />
            <span className="flex-1 truncate text-xs">{file.item_id}</span>
          </div>
        ))}
        {files.length === 0 && (
          <p className="py-3 text-center text-xs text-muted-foreground">
            No files attached
          </p>
        )}
      </div>
    </WorkspaceSection>
  )
}
