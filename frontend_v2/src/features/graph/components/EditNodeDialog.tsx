import { useState, useEffect, useMemo } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { NodeBadge } from "@/components/ui/node-badge"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import type { NodeDetail } from "@/types/graph.types"
import { graphAPI } from "../api"
import { useNodeDetails } from "../hooks/use-node-details"

interface EditNodeDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  nodeKey: string | null
  caseId: string
  onSaved?: () => void
}

interface EditableProperty {
  key: string
  label: string
  kind: "string" | "number"
  value: string
}

const hiddenPropertyKeys = new Set([
  "key",
  "label",
  "name",
  "type",
  "id",
  "summary",
  "notes",
  "ai_insights",
  "verified_facts",
  "case_id",
  "node_key",
  "mentioned",
  "confidence",
  "community_id",
])

function getEditableProperties(node: NodeDetail | undefined): EditableProperty[] {
  return Object.entries(node?.properties ?? {})
    .filter(([key, value]) => {
      if (hiddenPropertyKeys.has(key.toLowerCase())) return false
      return typeof value === "string" || typeof value === "number"
    })
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([key, value]) => ({
      key,
      label: key.replace(/_/g, " "),
      kind: typeof value === "number" ? "number" : "string",
      value: String(value ?? ""),
    }))
}

export function EditNodeDialog({ open, onOpenChange, nodeKey, caseId, onSaved }: EditNodeDialogProps) {
  const queryClient = useQueryClient()
  const { data: node, isLoading, error } = useNodeDetails(open ? nodeKey : null, caseId)
  const [name, setName] = useState("")
  const [summary, setSummary] = useState("")
  const [propertyValues, setPropertyValues] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  const editableProperties = useMemo(() => getEditableProperties(node), [node])

  useEffect(() => {
    if (node && open) {
      setName(node.label)
      setSummary(String(node.summary ?? ""))
      setPropertyValues(
        Object.fromEntries(
          editableProperties.map((property) => [property.key, property.value])
        )
      )
      setSaveError(null)
    }
  }, [editableProperties, node, open])

  const handleSave = async () => {
    if (!node) return

    const properties: Record<string, string | number | null> = {}
    for (const property of editableProperties) {
      const rawValue = propertyValues[property.key] ?? ""
      const trimmedValue = rawValue.trim()
      if (property.kind === "number") {
        if (trimmedValue === "") {
          properties[property.key] = null
          continue
        }
        const parsed = Number(trimmedValue)
        if (Number.isNaN(parsed)) {
          setSaveError(`"${property.label}" must be a number.`)
          return
        }
        properties[property.key] = parsed
        continue
      }
      properties[property.key] = rawValue === "" ? null : rawValue
    }

    setSaving(true)
    setSaveError(null)
    try {
      await graphAPI.updateNode(node.key, {
        name: name.trim(),
        summary,
        properties,
        case_id: caseId,
      })
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["graph", caseId] }),
        queryClient.invalidateQueries({ queryKey: ["graph", "node", node.key, caseId] }),
      ])
      onSaved?.()
      onOpenChange(false)
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Failed to save entity changes.")
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[85vh] w-[92vw] flex-col overflow-hidden gap-0 p-0 sm:max-w-5xl">
        <DialogHeader className="shrink-0 border-b border-border px-6 py-4">
          <DialogTitle className="flex items-center gap-2">
            {node ? <NodeBadge type={node.type} /> : null}
            Edit Entity
          </DialogTitle>
        </DialogHeader>
        {isLoading ? (
          <div className="flex min-h-40 items-center justify-center">
            <LoadingSpinner />
          </div>
        ) : !node ? (
          <div className="m-6 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {error instanceof Error ? error.message : "Unable to load entity details."}
          </div>
        ) : (
          <div className="min-h-0 flex-1 overflow-y-auto px-6 py-4">
            <div className="space-y-3">
              <div>
                <label className="mb-1 block text-xs font-medium">Name</label>
                <Input value={name} onChange={(e) => setName(e.target.value)} />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium">Summary</label>
                <Textarea
                  value={summary}
                  onChange={(e) => setSummary(e.target.value)}
                  placeholder="Add a short summary..."
                  className="min-h-32"
                />
              </div>
              {editableProperties.length > 0 && (
                <div className="space-y-3">
                  <p className="text-xs font-medium text-muted-foreground">
                    Entity Properties
                  </p>
                  {editableProperties.map((property) => (
                    <div key={property.key}>
                      <label className="mb-1 block text-xs font-medium capitalize">
                        {property.label}
                      </label>
                      <Input
                        type={property.kind === "number" ? "number" : "text"}
                        value={propertyValues[property.key] ?? ""}
                        onChange={(e) =>
                          setPropertyValues((current) => ({
                            ...current,
                            [property.key]: e.target.value,
                          }))
                        }
                      />
                    </div>
                  ))}
                </div>
              )}
              {saveError && (
                <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
                  {saveError}
                </div>
              )}
            </div>
          </div>
        )}
        <DialogFooter className="shrink-0 border-t border-border px-6 py-4">
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button
            variant="primary"
            onClick={handleSave}
            disabled={!node || !name.trim() || saving || isLoading}
          >
            {saving ? "Saving..." : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
