import { useState } from "react"
import { Plus, Palette } from "lucide-react"
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
import type { FinancialCategory } from "../api"

const PRESET_COLORS = [
  "#f59e0b", "#3b82f6", "#10b981", "#ef4444", "#8b5cf6",
  "#ec4899", "#06b6d4", "#84cc16", "#f97316", "#6366f1",
]

interface CategoryManagementDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  categories: FinancialCategory[]
  onCreateCategory: (name: string, color: string) => void
}

export function CategoryManagementDialog({
  open,
  onOpenChange,
  categories,
  onCreateCategory,
}: CategoryManagementDialogProps) {
  const [newName, setNewName] = useState("")
  const [newColor, setNewColor] = useState(PRESET_COLORS[0])

  const handleCreate = () => {
    if (!newName.trim()) return
    onCreateCategory(newName.trim(), newColor)
    setNewName("")
    setNewColor(PRESET_COLORS[0])
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-sm">
            <Palette className="size-4" />
            Manage Categories
          </DialogTitle>
        </DialogHeader>

        {/* Existing categories */}
        <ScrollArea className="max-h-48">
          <div className="space-y-1">
            {categories.map((cat) => (
              <div
                key={cat.name}
                className="flex items-center gap-2 rounded-md border border-border px-3 py-2"
              >
                <div
                  className="size-3 rounded-full"
                  style={{ backgroundColor: cat.color }}
                />
                <span className="flex-1 text-sm">{cat.name}</span>
              </div>
            ))}
            {categories.length === 0 && (
              <p className="py-4 text-center text-xs text-muted-foreground">
                No categories yet
              </p>
            )}
          </div>
        </ScrollArea>

        {/* Create new */}
        <div className="space-y-2 border-t border-border pt-3">
          <p className="text-xs font-semibold">New Category</p>
          <div className="flex items-center gap-2">
            <Input
              placeholder="Category name"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              className="flex-1"
              onKeyDown={(e) => e.key === "Enter" && handleCreate()}
            />
          </div>
          <div className="flex flex-wrap gap-1.5">
            {PRESET_COLORS.map((color) => (
              <button
                key={color}
                onClick={() => setNewColor(color)}
                className="size-6 rounded-full border-2 transition"
                style={{
                  backgroundColor: color,
                  borderColor: newColor === color ? "white" : "transparent",
                }}
              />
            ))}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
            Close
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={handleCreate}
            disabled={!newName.trim()}
          >
            <Plus className="size-3.5" />
            Add Category
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
