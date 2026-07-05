import { BookOpenText, Loader2, NotebookPen, Plus } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/cn"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import { useUIStore } from "@/stores/ui.store"
import { useTargetNotebookNotes } from "../hooks/use-notebook"
import { useNotebookStore } from "../notebook.store"
import { notebookAuthorLabel } from "../lib/author-display"
import type { NotebookTargetType } from "../api"

interface NotebookLinkedNotesProps {
  caseId: string
  targetType: NotebookTargetType
  targetId: string
  targetLabel?: string | null
  className?: string
}

function titleForNote(note: { title?: string | null; body: string }) {
  return note.title?.trim() || note.body.split(/\r?\n/).find(Boolean)?.slice(0, 80) || "Untitled note"
}

export function NotebookLinkedNotes({
  caseId,
  targetType,
  targetId,
  targetLabel,
  className,
}: NotebookLinkedNotesProps) {
  const { data, isLoading } = useTargetNotebookNotes(caseId, targetType, targetId, 6)
  const openNote = useNotebookStore((s) => s.openNote)
  const startDraft = useNotebookStore((s) => s.startDraft)
  const expandGraphPanelTo = useUIStore((s) => s.expandGraphPanelTo)
  const user = useAuthStore((s) => s.user)

  const notes = data?.notes ?? []
  const total = data?.total ?? notes.length

  const openNotebookNote = (noteId: string) => {
    openNote(noteId)
    expandGraphPanelTo("notebook")
  }

  const startLinkedNote = () => {
    startDraft([
      {
        target_type: targetType,
        target_id: targetId,
        target_label: targetLabel || targetId,
      },
    ])
    expandGraphPanelTo("notebook")
  }

  return (
    <div className={cn("space-y-2", className)}>
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <NotebookPen className="size-3.5 text-muted-foreground" />
          <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Notebook
          </h4>
          {total > 0 && (
            <Badge variant="slate" className="px-1.5 py-0 text-[10px]">
              {total}
            </Badge>
          )}
        </div>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-6 px-2 text-[11px]"
          onClick={startLinkedNote}
        >
          <Plus className="size-3" />
          Add note
        </Button>
      </div>

      {isLoading ? (
        <div className="flex items-center gap-2 rounded-md border border-border bg-muted/20 px-3 py-2 text-xs text-muted-foreground">
          <Loader2 className="size-3.5 animate-spin" />
          Loading linked notes
        </div>
      ) : notes.length > 0 ? (
        <div className="space-y-1.5">
          {notes.slice(0, 3).map((note) => (
            <button
              key={note.id}
              type="button"
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-left transition-colors hover:border-slate-300 hover:bg-muted/30 dark:hover:border-slate-600"
              onClick={() => openNotebookNote(note.id)}
            >
              <div className="flex min-w-0 items-center justify-between gap-2">
                <p className="min-w-0 truncate text-xs font-semibold text-foreground">
                  {titleForNote(note)}
                </p>
                <span className="shrink-0 text-[10px] text-muted-foreground">
                  {notebookAuthorLabel(note, user)}
                </span>
              </div>
              <p className="mt-0.5 line-clamp-2 text-[11px] leading-relaxed text-muted-foreground">
                {note.body}
              </p>
            </button>
          ))}
          {total > 3 && (
            <button
              type="button"
              className="text-[11px] font-medium text-muted-foreground hover:text-foreground"
              onClick={() => {
                expandGraphPanelTo("notebook")
              }}
            >
              View {total - 3} more in Notebook
            </button>
          )}
        </div>
      ) : (
        <button
          type="button"
          className="flex w-full items-center gap-2 rounded-md border border-dashed border-border bg-muted/10 px-3 py-2 text-left text-xs text-muted-foreground transition-colors hover:border-slate-300 hover:bg-muted/30 hover:text-foreground dark:hover:border-slate-600"
          onClick={startLinkedNote}
        >
          <BookOpenText className="size-3.5 shrink-0" />
          No notes linked to this item yet.
        </button>
      )}
    </div>
  )
}
