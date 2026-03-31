import { useState } from "react"
import { StickyNote, Plus, Trash2, Tag } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Badge } from "@/components/ui/badge"
import { useNotes, useCreateNote, useDeleteNote } from "../hooks/use-workspace"

interface InvestigativeNotesSectionProps {
  caseId: string
}

export function InvestigativeNotesSection({ caseId }: InvestigativeNotesSectionProps) {
  const { data: notes = [], isLoading } = useNotes(caseId)
  const createMutation = useCreateNote(caseId)
  const deleteMutation = useDeleteNote(caseId)

  const [showAdd, setShowAdd] = useState(false)
  const [title, setTitle] = useState("")
  const [content, setContent] = useState("")
  const [tagsInput, setTagsInput] = useState("")

  const handleAdd = () => {
    if (!title.trim()) return
    const tags = tagsInput
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean)
    createMutation.mutate(
      { title, content, tags },
      {
        onSuccess: () => {
          setShowAdd(false)
          setTitle("")
          setContent("")
          setTagsInput("")
        },
      },
    )
  }

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <StickyNote className="size-4 text-yellow-500" />
          <h3 className="text-xs font-semibold">Notes</h3>
          <Badge variant="slate" className="h-4 px-1.5 text-[10px]">
            {notes.length}
          </Badge>
        </div>
        <Button variant="ghost" size="sm" onClick={() => setShowAdd(!showAdd)}>
          <Plus className="size-3" />
        </Button>
      </div>

      {/* Add form */}
      {showAdd && (
        <div className="space-y-2 rounded-md border border-border p-2">
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
          <Input
            placeholder="Tags (comma-separated)"
            value={tagsInput}
            onChange={(e) => setTagsInput(e.target.value)}
            className="h-7 text-xs"
          />
          <div className="flex justify-end gap-1">
            <Button variant="ghost" size="sm" onClick={() => setShowAdd(false)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={handleAdd}
              disabled={!title.trim() || createMutation.isPending}
            >
              Save
            </Button>
          </div>
        </div>
      )}

      {/* Notes list */}
      {isLoading ? (
        <div className="space-y-2">
          {[1, 2].map((i) => (
            <div key={i} className="h-16 animate-pulse rounded-md bg-muted/30" />
          ))}
        </div>
      ) : (
        <div className="space-y-2">
          {notes.map((note) => (
            <div
              key={note.id}
              className="group rounded-md border border-border p-2.5"
            >
              <div className="flex items-start justify-between">
                <div className="min-w-0 flex-1">
                  {note.title && <p className="text-xs font-medium">{note.title}</p>}
                  <p className="mt-0.5 line-clamp-2 text-[11px] text-muted-foreground">
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
              {note.tags && note.tags.length > 0 && (
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {note.tags.map((tag) => (
                    <Badge key={tag} variant="outline" className="text-[9px]">
                      <Tag className="mr-0.5 size-2" />
                      {tag}
                    </Badge>
                  ))}
                </div>
              )}
              {note.updated_at && (
                <p className="mt-1 text-[10px] text-muted-foreground/60">
                  {new Date(note.updated_at).toLocaleDateString()}
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
      )}
    </div>
  )
}
