import { ChevronRight, Home } from "lucide-react"
import type { EvidenceFolder } from "@/types/evidence.types"

interface FolderBreadcrumbsProps {
  breadcrumbs: EvidenceFolder[]
  onNavigate: (folderId: string | null) => void
}

export function FolderBreadcrumbs({ breadcrumbs, onNavigate }: FolderBreadcrumbsProps) {
  return (
    <nav className="flex items-center gap-1 text-sm text-muted-foreground">
      <button
        onClick={() => onNavigate(null)}
        className="flex items-center gap-1 rounded px-1.5 py-0.5 hover:bg-muted hover:text-foreground transition-colors"
      >
        <Home className="size-3.5" />
        Root
      </button>
      {breadcrumbs.map((crumb) => (
        <span key={crumb.id} className="flex items-center gap-1">
          <ChevronRight className="size-3 text-muted-foreground/50" />
          <button
            onClick={() => onNavigate(crumb.id)}
            className="rounded px-1.5 py-0.5 hover:bg-muted hover:text-foreground transition-colors"
          >
            {crumb.name}
          </button>
        </span>
      ))}
    </nav>
  )
}
