import { Camera, Plus, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useSnapshots, useCreateSnapshot, useDeleteSnapshot } from "@/features/cases/hooks/use-snapshots"
import { WorkspaceSection } from "./WorkspaceSection"

interface SnapshotsSectionProps {
  caseId: string
}

export function SnapshotsSection({ caseId }: SnapshotsSectionProps) {
  const { data: snapshots = [] } = useSnapshots()
  const createMutation = useCreateSnapshot()
  const deleteMutation = useDeleteSnapshot()

  return (
    <WorkspaceSection
      title="Graph Snapshots"
      icon={Camera}
      count={snapshots.length}
      defaultOpen={false}
      actions={
        <Button
          variant="ghost"
          size="sm"
          onClick={() =>
            createMutation.mutate({
              name: `Snapshot ${snapshots.length + 1}`,
              subgraph: {},
              case_id: caseId,
            })
          }
          disabled={createMutation.isPending}
        >
          <Plus className="size-3" />
        </Button>
      }
    >
      <div className="space-y-1">
        {snapshots.map((snap) => (
          <div
            key={snap.id}
            className="group flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-muted/30"
          >
            <Camera className="size-3 text-muted-foreground" />
            <span className="flex-1 text-xs font-medium">{snap.name}</span>
            <span className="text-[10px] text-muted-foreground">
              {new Date(snap.created_at).toLocaleDateString()}
            </span>
            <Button
              variant="ghost"
              size="icon-sm"
              className="opacity-0 group-hover:opacity-100"
              onClick={() => deleteMutation.mutate(snap.id)}
            >
              <Trash2 className="size-3" />
            </Button>
          </div>
        ))}
        {snapshots.length === 0 && (
          <p className="py-3 text-center text-xs text-muted-foreground">
            No snapshots saved
          </p>
        )}
      </div>
    </WorkspaceSection>
  )
}
