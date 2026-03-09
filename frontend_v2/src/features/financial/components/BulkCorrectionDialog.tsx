import { useState } from "react"
import { AlertTriangle } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from "@/components/ui/dialog"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Badge } from "@/components/ui/badge"
import type { FinancialCategory } from "../api"

interface BulkCorrectionDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  selectedCount: number
  categories: FinancialCategory[]
  onApply: (category: string) => void
  isPending?: boolean
}

export function BulkCorrectionDialog({
  open,
  onOpenChange,
  selectedCount,
  categories,
  onApply,
  isPending,
}: BulkCorrectionDialogProps) {
  const [category, setCategory] = useState("")

  const handleApply = () => {
    if (!category) return
    onApply(category)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle className="text-sm">Bulk Categorize</DialogTitle>
          <DialogDescription className="text-xs">
            Apply a category to {selectedCount} selected transaction
            {selectedCount !== 1 ? "s" : ""}.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div className="flex items-center gap-2 rounded-md bg-amber-500/10 px-3 py-2">
            <AlertTriangle className="size-4 text-amber-500" />
            <p className="text-xs">
              This will overwrite existing categories on selected transactions.
            </p>
          </div>

          <div>
            <label className="mb-1 text-xs font-medium">Category</label>
            <Select value={category} onValueChange={setCategory}>
              <SelectTrigger>
                <SelectValue placeholder="Select category" />
              </SelectTrigger>
              <SelectContent>
                {categories.map((cat) => (
                  <SelectItem key={cat.name} value={cat.name}>
                    <div className="flex items-center gap-2">
                      <div
                        className="size-2 rounded-full"
                        style={{ backgroundColor: cat.color }}
                      />
                      {cat.name}
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <Badge variant="slate">{selectedCount} transactions selected</Badge>
        </div>

        <DialogFooter>
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={handleApply}
            disabled={!category || isPending}
          >
            {isPending ? "Applying..." : "Apply"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
