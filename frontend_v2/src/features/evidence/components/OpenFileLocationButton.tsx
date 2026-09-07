import { Link } from "react-router-dom"
import { FolderOpen } from "lucide-react"
import { Button } from "@/components/ui/button"

export function OpenFileLocationButton({
  caseId,
  evidenceId,
  onNavigate,
  compact = false,
}: {
  caseId: string
  evidenceId: string
  compact?: boolean
  onNavigate?: () => void
}) {
  const search = new URLSearchParams({ file: evidenceId, reveal: "1" })
  return (
    <Button asChild variant="ghost" size="sm">
      <Link
        to={`/cases/${encodeURIComponent(caseId)}/evidence?${search}`}
        onClick={(event) => {
          if (
            !event.metaKey &&
            !event.ctrlKey &&
            !event.shiftKey &&
            !event.altKey &&
            event.button === 0
          ) {
            onNavigate?.()
          }
        }}
        title="Open file location"
        aria-label="Open file location"
      >
        <FolderOpen className="size-4" />
        {!compact && <span className="hidden sm:inline">Open file location</span>}
      </Link>
    </Button>
  )
}
