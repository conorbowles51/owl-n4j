import { Paperclip } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { usePinnedItems } from "../hooks/use-workspace"

interface CaseFilesSectionProps {
  caseId: string
}

export function CaseFilesSection({ caseId }: CaseFilesSectionProps) {
  const { data: pinned = [] } = usePinnedItems(caseId)
  const files = pinned.filter((p) => p.item_type === "file")

  if (files.length === 0) return null

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <Paperclip className="size-3.5 text-muted-foreground" />
        <h3 className="text-xs font-semibold">Case Files</h3>
        <Badge variant="slate" className="h-4 px-1.5 text-[10px]">
          {files.length}
        </Badge>
      </div>
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
      </div>
    </div>
  )
}
