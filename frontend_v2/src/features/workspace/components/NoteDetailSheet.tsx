import { useEffect, useMemo, useState } from "react"
import { useNavigate } from "react-router-dom"
import { Loader2, Network, Save, Trash2 } from "lucide-react"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Badge } from "@/components/ui/badge"
import type { InvestigativeNote } from "../api"
import {
  useBuildWorkspaceGraph,
  useDeleteNote,
  useUpdateNote,
} from "../hooks/use-workspace"
import { formatWorkspaceDateTime } from "../lib/format-date"

interface NoteDetailSheetProps {
  caseId: string
  note: InvestigativeNote | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function NoteDetailSheet({
  caseId,
  note,
  open,
  onOpenChange,
}: NoteDetailSheetProps) {
  const navigate = useNavigate()
  const updateNote = useUpdateNote(caseId)
  const deleteNote = useDeleteNote(caseId)
  const buildGraph = useBuildWorkspaceGraph(caseId)

  const [title, setTitle] = useState("")
  const [content, setContent] = useState("")
  const [tagsInput, setTagsInput] = useState("")

  useEffect(() => {
    if (!note) return
    setTitle(note.title ?? "")
    setContent(note.content ?? "")
    setTagsInput((note.tags ?? []).join(", "))
  }, [note])

  const isDirty = useMemo(() => {
    if (!note) return false
    return (
      title !== (note.title ?? "") ||
      content !== (note.content ?? "") ||
      tagsInput !== (note.tags ?? []).join(", ")
    )
  }, [content, note, tagsInput, title])

  const handleOpenChange = (nextOpen: boolean) => {
    if (!nextOpen && isDirty) return
    onOpenChange(nextOpen)
  }

  const tags = tagsInput
    .split(",")
    .map((tag) => tag.trim())
    .filter(Boolean)

  const handleSave = () => {
    if (!note) return
    updateNote.mutate(
      {
        noteId: note.id,
        updates: {
          title: title.trim() || undefined,
          content,
          tags,
        },
      },
      { onSuccess: () => onOpenChange(false) },
    )
  }

  const handleBuildGraph = () => {
    if (!note) return
    buildGraph.mutate(
      {
        source_type: "note",
        source_id: note.id,
      },
      {
        onSuccess: (result) => {
          navigate(`/cases/${caseId}/graph`, {
            state: {
              workspaceGraphSource: {
                sourceType: "note",
                sourceId: note.id,
                sourceLabel: note.title || "Investigative Note",
                entityKeys: result.entity_keys,
              },
            },
          })
        },
      },
    )
  }

  if (!note) return null

  return (
    <Sheet open={open} onOpenChange={handleOpenChange}>
      <SheetContent
        side="right"
        className="flex w-full flex-col sm:max-w-lg"
        onInteractOutside={(event) => {
          if (isDirty) event.preventDefault()
        }}
        onEscapeKeyDown={(event) => {
          if (isDirty) event.preventDefault()
        }}
      >
        <SheetHeader>
          <SheetTitle>Investigative Note</SheetTitle>
          <SheetDescription>
            Edit note content, tags, and build a graph from the note.
          </SheetDescription>
        </SheetHeader>

        <div className="flex-1 space-y-4 overflow-y-auto px-4">
          <div className="space-y-2">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Title
            </p>
            <Input value={title} onChange={(event) => setTitle(event.target.value)} />
          </div>

          <div className="space-y-2">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Content
            </p>
            <Textarea
              rows={10}
              value={content}
              onChange={(event) => setContent(event.target.value)}
            />
          </div>

          <div className="space-y-2">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Tags
            </p>
            <Input
              value={tagsInput}
              onChange={(event) => setTagsInput(event.target.value)}
              placeholder="Comma separated tags"
            />
            {tags.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {tags.map((tag) => (
                  <Badge key={tag} variant="outline" className="text-[10px]">
                    {tag}
                  </Badge>
                ))}
              </div>
            )}
          </div>

          {note.updated_at && (
            <p className="text-[10px] text-muted-foreground">
              Updated {formatWorkspaceDateTime(note.updated_at)}
            </p>
          )}
        </div>

        <SheetFooter className="flex-row gap-2 border-t px-4 py-3">
          <Button
            variant="danger"
            size="sm"
            onClick={() =>
              deleteNote.mutate(note.id, { onSuccess: () => onOpenChange(false) })
            }
          >
            <Trash2 className="mr-1.5 size-3.5" />
            Delete
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={handleBuildGraph}
            disabled={buildGraph.isPending}
          >
            {buildGraph.isPending ? (
              <Loader2 className="mr-1.5 size-3.5 animate-spin" />
            ) : (
              <Network className="mr-1.5 size-3.5" />
            )}
            Build Graph
          </Button>
          <div className="flex-1" />
          <Button size="sm" onClick={handleSave} disabled={updateNote.isPending}>
            {updateNote.isPending ? (
              <Loader2 className="mr-1.5 size-3.5 animate-spin" />
            ) : (
              <Save className="mr-1.5 size-3.5" />
            )}
            Save
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  )
}
