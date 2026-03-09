import { useState } from "react"
import { FileText, Edit2, Save } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { workspaceAPI } from "../api"
import { WorkspaceSection } from "./WorkspaceSection"

interface CaseContextSectionProps {
  caseId: string
}

export function CaseContextSection({ caseId }: CaseContextSectionProps) {
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [summary, setSummary] = useState("")

  const { data: context } = useQuery({
    queryKey: ["workspace", caseId, "context"],
    queryFn: () => workspaceAPI.getCaseContext(caseId),
  })

  const updateMutation = useMutation({
    mutationFn: (newSummary: string) =>
      workspaceAPI.updateCaseContext(caseId, { ...context, summary: newSummary }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workspace", caseId, "context"] })
      setEditing(false)
    },
  })

  const handleEdit = () => {
    setSummary(context?.summary || "")
    setEditing(true)
  }

  return (
    <WorkspaceSection
      title="Case Context"
      icon={FileText}
      actions={
        editing ? (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => updateMutation.mutate(summary)}
            disabled={updateMutation.isPending}
          >
            <Save className="size-3" />
          </Button>
        ) : (
          <Button variant="ghost" size="sm" onClick={handleEdit}>
            <Edit2 className="size-3" />
          </Button>
        )
      }
    >
      {editing ? (
        <Textarea
          value={summary}
          onChange={(e) => setSummary(e.target.value)}
          placeholder="Describe the case context..."
          rows={4}
        />
      ) : (
        <div className="space-y-2">
          <p className="text-xs text-muted-foreground">
            {context?.summary || "No context set. Click edit to add a summary."}
          </p>
          {context?.objectives && context.objectives.length > 0 && (
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                Objectives
              </p>
              <ul className="mt-1 space-y-0.5">
                {context.objectives.map((obj, i) => (
                  <li key={i} className="text-xs">
                    • {obj}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </WorkspaceSection>
  )
}
