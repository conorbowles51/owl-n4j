import { useState } from "react"
import { Users, Plus, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { workspaceAPI, type Witness } from "../api"
import { WorkspaceSection } from "./WorkspaceSection"

interface WitnessMatrixSectionProps {
  caseId: string
}

export function WitnessMatrixSection({ caseId }: WitnessMatrixSectionProps) {
  const queryClient = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const [name, setName] = useState("")
  const [role, setRole] = useState("")

  const { data: witnesses = [] } = useQuery({
    queryKey: ["workspace", caseId, "witnesses"],
    queryFn: () => workspaceAPI.getWitnesses(caseId),
  })

  const createMutation = useMutation({
    mutationFn: (witness: Omit<Witness, "id">) =>
      workspaceAPI.createWitness(caseId, witness),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workspace", caseId, "witnesses"] })
      setShowAdd(false)
      setName("")
      setRole("")
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (witnessId: string) =>
      workspaceAPI.deleteWitness(caseId, witnessId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workspace", caseId, "witnesses"] })
    },
  })

  return (
    <WorkspaceSection
      title="Witnesses"
      icon={Users}
      count={witnesses.length}
      actions={
        <Button variant="ghost" size="sm" onClick={() => setShowAdd(!showAdd)}>
          <Plus className="size-3" />
        </Button>
      }
    >
      {showAdd && (
        <div className="mb-3 flex items-center gap-2 rounded-md border border-border p-2">
          <Input
            placeholder="Name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="h-7 text-xs"
          />
          <Input
            placeholder="Role"
            value={role}
            onChange={(e) => setRole(e.target.value)}
            className="h-7 w-32 text-xs"
          />
          <Button
            variant="primary"
            size="sm"
            onClick={() => {
              if (name.trim()) createMutation.mutate({ name, role })
            }}
            disabled={!name.trim() || createMutation.isPending}
          >
            Add
          </Button>
        </div>
      )}
      <div className="space-y-1">
        {witnesses.map((w) => (
          <div
            key={w.id}
            className="group flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-muted/30"
          >
            <Users className="size-3 text-muted-foreground" />
            <span className="flex-1 text-xs font-medium">{w.name}</span>
            {w.role && (
              <Badge variant="outline" className="text-[10px]">
                {w.role}
              </Badge>
            )}
            {w.status && (
              <Badge variant="slate" className="text-[10px]">
                {w.status}
              </Badge>
            )}
            <Button
              variant="ghost"
              size="icon-sm"
              className="opacity-0 group-hover:opacity-100"
              onClick={() => deleteMutation.mutate(w.id)}
            >
              <Trash2 className="size-3" />
            </Button>
          </div>
        ))}
        {witnesses.length === 0 && (
          <p className="py-3 text-center text-xs text-muted-foreground">
            No witnesses added
          </p>
        )}
      </div>
    </WorkspaceSection>
  )
}
