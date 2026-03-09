import { useState } from "react"
import { StickyNote, Plus, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { workspaceAPI, type InvestigativeNote } from "../api"
import { WorkspaceSection } from "./WorkspaceSection"

interface InvestigativeNotesSectionProps {
  caseId: string
}

export function InvestigativeNotesSection({ caseId }: InvestigativeNotesSectionProps) {
  const queryClient = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const [title, setTitle] = useState("")
  const [content, setContent] = useState("")

  const { data: notes = [] } = useQuery({
    queryKey: ["workspace", caseId, "notes"],
    queryFn: () => workspaceAPI.getNotes(caseId),
  })

  const createMutation = useMutation({
    mutationFn: (note: Omit<InvestigativeNote, "id">) =>
      workspaceAPI.createNote(caseId, note),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workspace", caseId, "notes"] })
      setShowAdd(false)
      setTitle("")
      setContent("")
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (noteId: string) => workspaceAPI.deleteNote(caseId, noteId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workspace", caseId, "notes"] })
    },
  })

  return (
    <WorkspaceSection
      title="Investigative Notes"
      icon={StickyNote}
      count={notes.length}
      actions={
        <Button variant="ghost" size="sm" onClick={() => setShowAdd(!showAdd)}>
          <Plus className="size-3" />
        </Button>
      }
    >
      {showAdd && (
        <div className="mb-3 space-y-2 rounded-md border border-border p-2">
          <Input
            placeholder="Note title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="h-7 text-xs"
          />
          <Textarea
            placeholder="Note content..."
            value={content}
            onChange={(e) => setContent(e.target.value)}
            rows={3}
            className="text-xs"
          />
          <div className="flex justify-end gap-1">
            <Button variant="ghost" size="sm" onClick={() => setShowAdd(false)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={() => {
                if (title.trim()) createMutation.mutate({ title, content })
              }}
              disabled={!title.trim() || createMutation.isPending}
            >
              Save
            </Button>
          </div>
        </div>
      )}
      <div className="space-y-2">
        {notes.map((note) => (
          <div
            key={note.id}
            className="group rounded-md border border-border p-2.5"
          >
            <div className="flex items-start justify-between">
              <div className="min-w-0 flex-1">
                <p className="text-xs font-medium">{note.title}</p>
                <p className="mt-1 line-clamp-2 text-[11px] text-muted-foreground">
                  {note.content}
                </p>
              </div>
              <Button
                variant="ghost"
                size="icon-sm"
                className="opacity-0 group-hover:opacity-100"
                onClick={() => deleteMutation.mutate(note.id)}
              >
                <Trash2 className="size-3" />
              </Button>
            </div>
            {note.updated_at && (
              <p className="mt-1 text-[10px] text-muted-foreground">
                Updated {new Date(note.updated_at).toLocaleDateString()}
              </p>
            )}
          </div>
        ))}
        {notes.length === 0 && (
          <p className="py-3 text-center text-xs text-muted-foreground">
            No notes yet
          </p>
        )}
      </div>
    </WorkspaceSection>
  )
}
