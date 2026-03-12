import { useState } from "react"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { graphAPI } from "@/features/graph/api"

interface BulkEditDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  entityKeys: string[]
  knownProperties: string[]
  onComplete: () => void
}

export function BulkEditDialog({
  open,
  onOpenChange,
  entityKeys,
  knownProperties,
  onComplete,
}: BulkEditDialogProps) {
  const [propertyKey, setPropertyKey] = useState("")
  const [customKey, setCustomKey] = useState("")
  const [value, setValue] = useState("")
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const effectiveKey = propertyKey === "_custom" ? customKey.trim() : propertyKey

  const handleSave = async () => {
    if (!effectiveKey || !value.trim()) return

    setSaving(true)
    setError(null)
    try {
      await Promise.all(
        entityKeys.map((key) =>
          graphAPI.updateNode(key, { properties: { [effectiveKey]: value.trim() } })
        )
      )
      onComplete()
      onOpenChange(false)
      setPropertyKey("")
      setCustomKey("")
      setValue("")
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update entities")
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Bulk Edit Entities</DialogTitle>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="flex items-center gap-2">
            <Badge variant="secondary">{entityKeys.length} entities</Badge>
            <span className="text-xs text-muted-foreground">will be updated</span>
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium">Property</label>
            <Select value={propertyKey} onValueChange={setPropertyKey}>
              <SelectTrigger>
                <SelectValue placeholder="Select a property..." />
              </SelectTrigger>
              <SelectContent>
                {knownProperties.map((prop) => (
                  <SelectItem key={prop} value={prop}>
                    {prop}
                  </SelectItem>
                ))}
                <SelectItem value="_custom">Custom property...</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {propertyKey === "_custom" && (
            <div className="space-y-2">
              <label className="text-sm font-medium">Custom Property Name</label>
              <Input
                value={customKey}
                onChange={(e) => setCustomKey(e.target.value)}
                placeholder="Enter property name..."
              />
            </div>
          )}

          <div className="space-y-2">
            <label className="text-sm font-medium">Value</label>
            <Input
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder="Enter value..."
            />
          </div>

          {error && (
            <p className="text-sm text-destructive">{error}</p>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleSave}
            disabled={!effectiveKey || !value.trim() || saving}
          >
            {saving ? "Updating..." : `Update ${entityKeys.length} entities`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
