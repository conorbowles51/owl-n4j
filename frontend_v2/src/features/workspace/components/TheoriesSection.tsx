import { useState } from "react"
import { Lightbulb, Plus, Trash2, ThumbsUp, ThumbsDown } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Badge } from "@/components/ui/badge"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { workspaceAPI, type Theory } from "../api"
import { WorkspaceSection } from "./WorkspaceSection"

interface TheoriesSectionProps {
  caseId: string
}

export function TheoriesSection({ caseId }: TheoriesSectionProps) {
  const queryClient = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const [newTitle, setNewTitle] = useState("")
  const [newDesc, setNewDesc] = useState("")

  const { data: theories = [] } = useQuery({
    queryKey: ["workspace", caseId, "theories"],
    queryFn: () => workspaceAPI.getTheories(caseId),
  })

  const createMutation = useMutation({
    mutationFn: (theory: Omit<Theory, "id">) =>
      workspaceAPI.createTheory(caseId, theory),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workspace", caseId, "theories"] })
      setShowAdd(false)
      setNewTitle("")
      setNewDesc("")
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (theoryId: string) =>
      workspaceAPI.deleteTheory(caseId, theoryId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workspace", caseId, "theories"] })
    },
  })

  const handleAdd = () => {
    if (!newTitle.trim()) return
    createMutation.mutate({ title: newTitle, description: newDesc })
  }

  return (
    <WorkspaceSection
      title="Theories"
      icon={Lightbulb}
      count={theories.length}
      actions={
        <Button variant="ghost" size="sm" onClick={() => setShowAdd(!showAdd)}>
          <Plus className="size-3" />
        </Button>
      }
    >
      {showAdd && (
        <div className="mb-3 space-y-2 rounded-md border border-border p-2">
          <Input
            placeholder="Theory title"
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            className="h-7 text-xs"
          />
          <Textarea
            placeholder="Description..."
            value={newDesc}
            onChange={(e) => setNewDesc(e.target.value)}
            rows={2}
            className="text-xs"
          />
          <div className="flex justify-end gap-1">
            <Button variant="ghost" size="sm" onClick={() => setShowAdd(false)}>
              Cancel
            </Button>
            <Button variant="primary" size="sm" onClick={handleAdd} disabled={createMutation.isPending}>
              Add
            </Button>
          </div>
        </div>
      )}
      <div className="space-y-2">
        {theories.map((theory) => (
          <div
            key={theory.id}
            className="rounded-md border border-border p-2.5"
          >
            <div className="flex items-start justify-between">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <p className="text-xs font-medium">{theory.title}</p>
                  {theory.status && (
                    <Badge variant="outline" className="text-[10px]">
                      {theory.status}
                    </Badge>
                  )}
                </div>
                {theory.description && (
                  <p className="mt-1 text-[11px] text-muted-foreground">
                    {theory.description}
                  </p>
                )}
              </div>
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={() => deleteMutation.mutate(theory.id)}
              >
                <Trash2 className="size-3" />
              </Button>
            </div>
            {(theory.evidence_for?.length || theory.evidence_against?.length) && (
              <div className="mt-2 flex gap-3 text-[10px]">
                {theory.evidence_for && theory.evidence_for.length > 0 && (
                  <span className="flex items-center gap-1 text-emerald-500">
                    <ThumbsUp className="size-2.5" />
                    {theory.evidence_for.length} supporting
                  </span>
                )}
                {theory.evidence_against && theory.evidence_against.length > 0 && (
                  <span className="flex items-center gap-1 text-red-500">
                    <ThumbsDown className="size-2.5" />
                    {theory.evidence_against.length} against
                  </span>
                )}
              </div>
            )}
          </div>
        ))}
        {theories.length === 0 && (
          <p className="py-3 text-center text-xs text-muted-foreground">
            No theories yet
          </p>
        )}
      </div>
    </WorkspaceSection>
  )
}
