import { FolderPlus, PanelLeftClose } from "lucide-react"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { Tooltip, TooltipTrigger, TooltipContent } from "@/components/ui/tooltip"
import { useFolderTree } from "../hooks/use-folder-tree"
import { useEvidenceStore } from "../evidence.store"
import { FolderTreeNode } from "./FolderTreeNode"

interface FolderTreeSidebarProps {
  caseId: string
  onCreateFolder: (parentId: string | null) => void
  onDeleteFolder: (id: string, name: string, fileCount: number) => void
}

export function FolderTreeSidebar({
  caseId,
  onCreateFolder,
  onDeleteFolder,
}: FolderTreeSidebarProps) {
  const { data: tree, isLoading } = useFolderTree(caseId)
  const { currentFolderId, setCurrentFolder } = useEvidenceStore()

  return (
    <div className="flex h-full flex-col border-r border-border bg-muted/30">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-3 py-2">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Folders
        </h3>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon-sm"
              className="size-6"
              aria-label="Collapse sidebar"
            >
              <PanelLeftClose className="size-3.5" />
            </Button>
          </TooltipTrigger>
          <TooltipContent side="right">Collapse sidebar</TooltipContent>
        </Tooltip>
      </div>

      {/* Root item */}
      <button
        onClick={() => setCurrentFolder(null)}
        className={`mx-2 mt-2 flex items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors ${
          currentFolderId === null
            ? "bg-amber-500/10 text-amber-500 font-medium"
            : "text-muted-foreground hover:bg-muted hover:text-foreground"
        }`}
      >
        <span className="text-xs">All Files</span>
      </button>

      {/* Tree */}
      <ScrollArea className="flex-1 px-1 py-1">
        {isLoading ? (
          <div className="flex justify-center py-8">
            <LoadingSpinner size="sm" />
          </div>
        ) : (
          <div className="space-y-0.5">
            {tree?.map((node) => (
              <FolderTreeNode
                key={node.id}
                node={node}
                depth={0}
                caseId={caseId}
                onCreateFolder={onCreateFolder}
                onDeleteFolder={onDeleteFolder}
              />
            ))}
          </div>
        )}
      </ScrollArea>

      {/* Footer: New Folder button */}
      <div className="border-t border-border p-2">
        <Button
          variant="ghost"
          size="sm"
          className="w-full justify-start gap-2 text-xs text-muted-foreground hover:text-foreground"
          onClick={() => onCreateFolder(currentFolderId)}
        >
          <FolderPlus className="size-3.5" />
          New Folder
        </Button>
      </div>
    </div>
  )
}
