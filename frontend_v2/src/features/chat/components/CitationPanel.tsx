import { X, FileText } from "lucide-react"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"

interface CitationPanelProps {
  filename: string
  onClose: () => void
}

export function CitationPanel({ filename, onClose }: CitationPanelProps) {
  return (
    <div className="flex w-80 flex-col border-l border-border">
      <div className="flex items-center gap-2 border-b border-border px-3 py-2">
        <FileText className="size-3.5 text-amber-500" />
        <span className="flex-1 truncate text-xs font-semibold">{filename}</span>
        <Button variant="ghost" size="icon-sm" onClick={onClose}>
          <X className="size-3.5" />
        </Button>
      </div>
      <ScrollArea className="flex-1">
        <div className="p-4">
          <p className="text-xs text-muted-foreground">
            Source document preview for <strong>{filename}</strong>.
          </p>
          <p className="mt-2 text-xs text-muted-foreground">
            Full document viewer will be integrated with the evidence system.
          </p>
        </div>
      </ScrollArea>
    </div>
  )
}
