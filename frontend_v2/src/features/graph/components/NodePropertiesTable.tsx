import { ScrollArea } from "@/components/ui/scroll-area"
import { cn } from "@/lib/cn"

interface NodePropertiesTableProps {
  properties: Record<string, unknown>
  className?: string
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "—"
  if (typeof value === "boolean") return value ? "Yes" : "No"
  if (typeof value === "number") return String(value)
  if (Array.isArray(value)) return value.join(", ")
  if (typeof value === "object") return JSON.stringify(value)
  return String(value)
}

// Filter out internal/display keys
const hiddenKeys = new Set(["key", "label", "type", "x", "y", "case_id", "node_key"])

export function NodePropertiesTable({ properties, className }: NodePropertiesTableProps) {
  const entries = Object.entries(properties).filter(
    ([key, value]) => !hiddenKeys.has(key) && value !== null && value !== undefined && value !== ""
  )

  if (entries.length === 0) {
    return (
      <p className="py-3 text-center text-xs text-muted-foreground">
        No properties
      </p>
    )
  }

  return (
    <ScrollArea className={cn("max-h-[300px]", className)}>
      <div className="space-y-0.5">
        {entries.map(([key, value]) => (
          <div
            key={key}
            className="flex items-start gap-3 rounded px-2 py-1.5 hover:bg-muted/50"
          >
            <span className="min-w-[100px] shrink-0 text-xs font-medium text-muted-foreground">
              {key.replace(/_/g, " ")}
            </span>
            <span className="min-w-0 flex-1 break-words text-xs text-foreground">
              {formatValue(value)}
            </span>
          </div>
        ))}
      </div>
    </ScrollArea>
  )
}
