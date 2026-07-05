import { ScrollArea } from "@/components/ui/scroll-area"
import { cn } from "@/lib/cn"
import { ChevronDown } from "lucide-react"

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

const metadataKeys = new Set([
  "id",
  "key",
  "label",
  "name",
  "summary",
  "notes",
  "specific_type",
  "type",
  "x",
  "y",
  "case_id",
  "node_key",
  "job_id",
  "source_file",
  "source_files",
  "source_quote",
  "source_quotes",
  "verified_facts",
  "ai_insights",
  "confidence",
  "mentioned",
  "community_id",
  "embedding",
  "embedding_id",
  "vector_id",
  "system_node",
  "manual_fields",
  "last_edited_at",
  "last_edited_by",
  "last_edit_source",
  "geocoding_status",
  "geocoding_confidence",
  "geocode_confidence",
  "geocode_source",
  "geocode_accuracy",
  "formatted_address",
  "nearest_location_key",
  "nearest_location_lat",
  "nearest_location_lon",
  "nearest_location_delta_s",
  "nearest_location_source",
  "location_source",
])

export function NodePropertiesTable({ properties, className }: NodePropertiesTableProps) {
  const visibleEntries = Object.entries(properties).filter(
    ([key, value]) => !metadataKeys.has(key.toLowerCase()) && value !== null && value !== undefined && value !== ""
  )
  const metadataEntries = Object.entries(properties).filter(
    ([key, value]) => metadataKeys.has(key.toLowerCase()) && value !== null && value !== undefined && value !== ""
  )

  if (visibleEntries.length === 0 && metadataEntries.length === 0) {
    return (
      <p className="py-3 text-center text-xs text-muted-foreground">
        No properties
      </p>
    )
  }

  return (
    <div className={cn("space-y-2", className)}>
      {visibleEntries.length > 0 ? (
        <ScrollArea className="max-h-[300px]">
          <div className="space-y-0.5">
            {visibleEntries.map(([key, value]) => (
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
      ) : (
        <p className="py-2 text-center text-xs text-muted-foreground">
          No editable properties
        </p>
      )}

      {metadataEntries.length > 0 && (
        <details className="group border-t border-border pt-2">
          <summary className="flex cursor-pointer list-none items-center gap-1.5 px-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            <ChevronDown className="size-3 transition-transform group-open:rotate-180" />
            Provenance / system metadata
          </summary>
          <div className="mt-2 space-y-0.5">
            {metadataEntries.map(([key, value]) => (
              <div key={key} className="flex items-start gap-3 rounded px-2 py-1.5">
                <span className="min-w-[100px] shrink-0 text-xs font-medium text-muted-foreground">
                  {key.replace(/_/g, " ")}
                </span>
                <span className="min-w-0 flex-1 break-words text-xs text-muted-foreground">
                  {formatValue(value)}
                </span>
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  )
}
