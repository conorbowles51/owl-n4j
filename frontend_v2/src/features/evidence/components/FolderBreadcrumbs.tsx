import { ChevronRight, Home } from "lucide-react"
import { useEvidenceDropTarget } from "../hooks/use-evidence-moves"

interface BreadcrumbItem {
  id: string
  name: string
}
interface FolderBreadcrumbsProps {
  breadcrumbs: BreadcrumbItem[]
  currentFolder: { id: string; name: string } | null
  onNavigate: (folderId: string | null) => void
}
function Crumb({
  id,
  name,
  current,
  onNavigate,
}: {
  id: string | null
  name: string
  current?: boolean
  onNavigate: (id: string | null) => void
}) {
  const drop = useEvidenceDropTarget(id)
  return (
    <button
      {...drop}
      onClick={() => onNavigate(id)}
      aria-current={current ? "page" : undefined}
      className="flex items-center gap-1 rounded px-1.5 py-0.5 text-xs hover:bg-muted hover:text-foreground aria-[current=page]:font-medium aria-[current=page]:text-foreground data-[drop-active=true]:bg-primary/15 data-[drop-active=true]:outline-2 data-[drop-active=true]:outline-primary"
    >
      {id === null && <Home className="size-3.5" />}
      {name}
    </button>
  )
}
export function FolderBreadcrumbs({
  breadcrumbs,
  currentFolder,
  onNavigate,
}: FolderBreadcrumbsProps) {
  return (
    <nav
      aria-label="Evidence folder path"
      className="flex flex-wrap items-center gap-1 text-sm text-muted-foreground"
    >
      <Crumb
        id={null}
        name="Evidence root"
        current={!currentFolder}
        onNavigate={onNavigate}
      />
      {[...breadcrumbs, ...(currentFolder ? [currentFolder] : [])].map(
        (crumb) => (
          <span key={crumb.id} className="flex items-center gap-1">
            <ChevronRight className="size-3 text-muted-foreground/50" />
            <Crumb
              {...crumb}
              current={crumb.id === currentFolder?.id}
              onNavigate={onNavigate}
            />
          </span>
        )
      )}
    </nav>
  )
}
