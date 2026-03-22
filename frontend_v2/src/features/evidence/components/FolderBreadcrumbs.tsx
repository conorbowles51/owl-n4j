import { ChevronRight, Home } from "lucide-react"

interface BreadcrumbItem {
  id: string
  name: string
}

interface FolderBreadcrumbsProps {
  breadcrumbs: BreadcrumbItem[]
  currentFolder: { id: string; name: string } | null
  onNavigate: (folderId: string | null) => void
}

export function FolderBreadcrumbs({
  breadcrumbs,
  currentFolder,
  onNavigate,
}: FolderBreadcrumbsProps) {
  return (
    <nav className="flex items-center gap-1 text-sm text-muted-foreground">
      {/* Root link */}
      <button
        onClick={() => onNavigate(null)}
        className="flex items-center gap-1 rounded px-1.5 py-0.5 hover:bg-muted hover:text-foreground transition-colors"
      >
        <Home className="size-3.5" />
        <span className="text-xs">Root</span>
      </button>

      {/* Breadcrumb trail */}
      {breadcrumbs.map((crumb) => (
        <span key={crumb.id} className="flex items-center gap-1">
          <ChevronRight className="size-3 text-muted-foreground/50" />
          <button
            onClick={() => onNavigate(crumb.id)}
            className="rounded px-1.5 py-0.5 text-xs hover:bg-muted hover:text-foreground transition-colors"
          >
            {crumb.name}
          </button>
        </span>
      ))}

      {/* Current folder (not clickable) */}
      {currentFolder && (
        <span className="flex items-center gap-1">
          <ChevronRight className="size-3 text-muted-foreground/50" />
          <span className="rounded px-1.5 py-0.5 text-xs font-medium text-foreground">
            {currentFolder.name}
          </span>
        </span>
      )}
    </nav>
  )
}
