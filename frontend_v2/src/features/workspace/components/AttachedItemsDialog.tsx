import { useState } from "react"
import { Link, Unlink, Search } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"
import { ScrollArea } from "@/components/ui/scroll-area"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { workspaceAPI } from "../api"

interface AttachedItemsDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  caseId: string
  itemType: string
  title: string
}

export function AttachedItemsDialog({
  open,
  onOpenChange,
  caseId,
  itemType,
  title,
}: AttachedItemsDialogProps) {
  const queryClient = useQueryClient()
  const [search, setSearch] = useState("")
  const [newItemId, setNewItemId] = useState("")

  const { data: pinned = [] } = useQuery({
    queryKey: ["workspace", caseId, "pinned"],
    queryFn: () => workspaceAPI.getPinnedItems(caseId),
    enabled: open,
  })

  const items = pinned.filter((p) => p.item_type === itemType)

  const pinMutation = useMutation({
    mutationFn: (itemId: string) =>
      workspaceAPI.pinItem(caseId, itemType, itemId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workspace", caseId, "pinned"] })
      setNewItemId("")
    },
  })

  const unpinMutation = useMutation({
    mutationFn: (pinId: string) => workspaceAPI.unpinItem(caseId, pinId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workspace", caseId, "pinned"] })
    },
  })

  const filtered = items.filter((i) =>
    i.item_id.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-sm">
            <Link className="size-4" />
            {title}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-3">
          {/* Search */}
          <div className="relative">
            <Search className="absolute left-2.5 top-2 size-3 text-muted-foreground" />
            <Input
              placeholder="Filter items..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-8"
            />
          </div>

          {/* Items list */}
          <ScrollArea className="max-h-48">
            <div className="space-y-1">
              {filtered.map((item) => (
                <div
                  key={item.id}
                  className="flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-muted"
                >
                  <span className="flex-1 truncate text-xs">{item.item_id}</span>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => unpinMutation.mutate(item.id)}
                  >
                    <Unlink className="size-3" />
                  </Button>
                </div>
              ))}
              {filtered.length === 0 && (
                <p className="py-4 text-center text-xs text-muted-foreground">
                  No items attached
                </p>
              )}
            </div>
          </ScrollArea>

          {/* Add new */}
          <div className="flex gap-1 border-t border-border pt-2">
            <Input
              placeholder="Item ID to attach"
              value={newItemId}
              onChange={(e) => setNewItemId(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && newItemId.trim()) {
                  pinMutation.mutate(newItemId.trim())
                }
              }}
              className="h-7 text-xs"
            />
            <Button
              variant="primary"
              size="sm"
              onClick={() => {
                if (newItemId.trim()) pinMutation.mutate(newItemId.trim())
              }}
              disabled={!newItemId.trim() || pinMutation.isPending}
            >
              Attach
            </Button>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
            Done
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
