import { useState, useEffect } from "react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { EmptyState } from "@/components/ui/empty-state"
import { NodeBadge } from "@/components/ui/node-badge"
import { Trash2, RotateCcw } from "lucide-react"
import { graphAPI } from "../api"
import type { RecycledEntity } from "@/types/graph.types"

interface RecycleBinPanelProps {
  caseId: string
}

export function RecycleBinPanel({ caseId }: RecycleBinPanelProps) {
  const [entities, setEntities] = useState<RecycledEntity[]>([])
  const [loading, setLoading] = useState(true)
  const [actionKey, setActionKey] = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    try {
      const data = await graphAPI.listRecycledEntities(caseId)
      setEntities(data.entities ?? [])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [caseId])

  const restore = async (key: string) => {
    setActionKey(key)
    try {
      await graphAPI.restoreRecycledEntity(key, caseId)
      setEntities((prev) => prev.filter((e) => e.key !== key))
    } finally {
      setActionKey(null)
    }
  }

  const permanentDelete = async (key: string) => {
    setActionKey(key)
    try {
      await graphAPI.permanentlyDeleteRecycled(key, caseId)
      setEntities((prev) => prev.filter((e) => e.key !== key))
    } finally {
      setActionKey(null)
    }
  }

  if (loading) {
    return (
      <div className="flex justify-center py-8">
        <LoadingSpinner />
      </div>
    )
  }

  if (entities.length === 0) {
    return (
      <EmptyState
        icon={Trash2}
        title="Recycle bin is empty"
        description="Deleted entities will appear here"
        className="py-8"
      />
    )
  }

  return (
    <div className="p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold">Recycle Bin</h3>
        <Badge variant="slate">{entities.length} items</Badge>
      </div>
      <ScrollArea className="max-h-[400px]">
        <div className="space-y-2">
          {entities.map((e) => (
            <div key={e.key} className="flex items-center gap-2 rounded-lg border p-2">
              <NodeBadge type={e.type} />
              <div className="min-w-0 flex-1">
                <p className="truncate text-xs font-medium">{e.name}</p>
                <p className="text-[10px] text-muted-foreground">
                  Deleted {new Date(e.deleted_at).toLocaleDateString()}
                </p>
              </div>
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={() => restore(e.key)}
                disabled={actionKey === e.key}
                title="Restore"
              >
                <RotateCcw className="size-3.5" />
              </Button>
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={() => permanentDelete(e.key)}
                disabled={actionKey === e.key}
                title="Delete permanently"
                className="text-red-400 hover:text-red-300"
              >
                <Trash2 className="size-3.5" />
              </Button>
            </div>
          ))}
        </div>
      </ScrollArea>
    </div>
  )
}
