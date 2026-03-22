import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from "@/components/ui/dialog"
import { ScrollArea } from "@/components/ui/scroll-area"
import type { TransactionEntity } from "../api"

interface EntityEditDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  field: "from" | "to"
  allEntities: TransactionEntity[]
  /** Keys of transactions being edited — single for 1, multiple for batch */
  transactionKeys: string[]
  onSave: (entity: { key?: string; name?: string }) => void
  isPending?: boolean
}

export function EntityEditDialog({
  open,
  onOpenChange,
  field,
  allEntities,
  transactionKeys,
  onSave,
  isPending,
}: EntityEditDialogProps) {
  const [search, setSearch] = useState("")
  const [customName, setCustomName] = useState("")

  const isBatch = transactionKeys.length > 1

  const filtered = allEntities.filter(
    (e) => e.name && e.name.toLowerCase().includes(search.toLowerCase())
  )

  const handleSelect = (entity: TransactionEntity) => {
    onSave({ key: entity.key || undefined, name: entity.name || undefined })
  }

  const handleCustom = () => {
    if (!customName.trim()) return
    onSave({ name: customName.trim() })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle className="text-sm">
            Set {field === "from" ? "Sender" : "Receiver"} Entity
          </DialogTitle>
          <DialogDescription className="text-xs">
            {isBatch
              ? `Apply to ${transactionKeys.length} selected transactions`
              : "Select or enter an entity"}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <Input
            placeholder="Search entities..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />

          <ScrollArea className="max-h-48">
            <div className="space-y-0.5">
              {filtered.slice(0, 30).map((entity) => (
                <button
                  key={entity.key || entity.name}
                  onClick={() => handleSelect(entity)}
                  disabled={isPending}
                  className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-xs hover:bg-muted disabled:opacity-50"
                >
                  <span className="flex-1 truncate text-left">
                    {entity.name}
                  </span>
                </button>
              ))}
              {search && filtered.length === 0 && (
                <p className="py-2 text-center text-xs text-muted-foreground">
                  No matching entities
                </p>
              )}
            </div>
          </ScrollArea>

          <div className="border-t border-border pt-2">
            <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Custom Name
            </p>
            <div className="flex gap-2">
              <Input
                value={customName}
                onChange={(e) => setCustomName(e.target.value)}
                placeholder="Enter entity name..."
                className="flex-1"
                onKeyDown={(e) => e.key === "Enter" && handleCustom()}
              />
              <Button
                variant="outline"
                size="sm"
                onClick={handleCustom}
                disabled={!customName.trim() || isPending}
              >
                {isPending ? "..." : "Set"}
              </Button>
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
