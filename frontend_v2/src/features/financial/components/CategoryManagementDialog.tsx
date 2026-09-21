import { useRef, useState } from "react"
import { useFinancialDraft } from "../stores/financial-drafts"
import { Plus, Palette } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog"
import { ScrollArea } from "@/components/ui/scroll-area"
import type { FinancialCategory } from "../api"

const PRESET_COLORS = [
  "#b41624",
  "#5571c8",
  "#2c8197",
  "#c25778",
  "#8060a9",
  "#bc4e78",
  "#26869e",
  "#6f8b45",
  "#c4653f",
  "#655fc0",
]

interface CategoryManagementDialogProps {
  caseId: string
  open: boolean
  onOpenChange: (open: boolean) => void
  categories: FinancialCategory[]
  onCreateCategory: (name: string, color: string) => Promise<unknown>
  sharedPayments?: boolean
  loading?: boolean
  loadError?: string
  onReload?: () => void
}

function CategoryManagementForm({
  caseId,
  open,
  onOpenChange,
  categories,
  onCreateCategory,
  sharedPayments = false,
  loading = false,
  loadError,
  onReload,
}: CategoryManagementDialogProps) {
  const [search, setSearch] = useState("")
  const visible = categories.filter((category) =>
    category.name.toLocaleLowerCase().includes(search.toLocaleLowerCase())
  )
  const [draft, setDraft, clearDraft] = useFinancialDraft(
    caseId,
    "evidence-category-create",
    { name: "", color: PRESET_COLORS[0] }
  )
  const { name: newName, color: newColor } = draft
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState("")
  const [saved, setSaved] = useState("")
  const locked = useRef(false)
  const duplicate = categories.some(
    (category) =>
      category.name.toLocaleLowerCase() === newName.trim().toLocaleLowerCase()
  )

  const handleCreate = async () => {
    if (
      locked.current ||
      saving ||
      loading ||
      loadError ||
      !newName.trim() ||
      duplicate
    )
      return
    locked.current = true
    setSaving(true)
    setError("")
    setSaved("")
    try {
      await onCreateCategory(newName.trim(), newColor)
      setSaved(
        `Category "${newName.trim()}" saved. ${sharedPayments ? "It is available across all cases. Choose it on a transaction or apply it to a selection." : "Choose it from a record's Category menu to apply it."}`
      )
      clearDraft()
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "The category could not be saved. Your draft is retained."
      )
    } finally {
      locked.current = false
      setSaving(false)
    }
  }
  const close = (next: boolean) => {
    if (!locked.current) onOpenChange(next)
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-sm">
            <Palette className="size-4" />
            Manage Categories
          </DialogTitle>
          <DialogDescription>
            {sharedPayments
              ? "Create categories for use across all cases. Assign them by clicking a transaction’s category, or select transactions to categorize them together."
              : "Use categories to organise other financial records. Create a category here, then choose it from a record's Category menu."}
          </DialogDescription>
        </DialogHeader>

        {/* Existing categories */}
        <Input
          aria-label="Search categories"
          placeholder="Search categories"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        {loading && <p role="status">Loading categories…</p>}
        {loadError && (
          <p role="alert">
            {loadError}{" "}
            <button className="underline" onClick={onReload}>
              Reload categories
            </button>
          </p>
        )}
        <ScrollArea className="h-48">
          <div className="space-y-1">
            {visible.map((cat) => (
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
            {!loading && !loadError && visible.length === 0 && (
              <p className="py-4 text-center text-xs text-muted-foreground">
                {search
                  ? "No categories match your search"
                  : "No categories yet"}
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
              aria-label="Category name"
              maxLength={120}
              disabled={saving}
              value={newName}
              onChange={(e) =>
                setDraft((current) => ({ ...current, name: e.target.value }))
              }
              className="flex-1"
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault()
                  void handleCreate()
                }
              }}
            />
          </div>
          <div className="flex flex-wrap gap-1.5">
            {PRESET_COLORS.map((color) => (
              <button
                key={color}
                onClick={() => setDraft((current) => ({ ...current, color }))}
                aria-label={`Category colour ${color}`}
                aria-pressed={newColor === color}
                disabled={saving}
                className="size-6 rounded-full border-2 transition"
                style={{
                  backgroundColor: color,
                  borderColor: newColor === color ? "white" : "transparent",
                }}
              />
            ))}
          </div>
        </div>

        {duplicate && (
          <p role="status" className="text-sm">
            This category already exists. Choose it from a record's Category
            menu.
          </p>
        )}
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}
        {saved && (
          <p role="status" className="text-sm">
            {saved}
          </p>
        )}
        <p className="text-xs text-muted-foreground">
          An unfinished name and colour stay in this browser tab until you save
          them.
        </p>
        <DialogFooter>
          <Button
            variant="outline"
            size="sm"
            disabled={saving}
            onClick={() => close(false)}
          >
            Close
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={handleCreate}
            disabled={
              !newName.trim() || duplicate || saving || loading || !!loadError
            }
          >
            <Plus className="size-3.5" />
            {saving ? "Saving..." : "Add Category"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function CategoryManagementDialog(props: CategoryManagementDialogProps) {
  return props.open ? (
    <CategoryManagementForm key={props.caseId} {...props} />
  ) : null
}
