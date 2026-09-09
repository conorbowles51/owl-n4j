import { useState } from "react"
import { FileImage, Loader2, Plus } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { useAttachmentOptions } from "@/features/workspace/hooks/use-casework"

export function DossierEvidencePicker({
  caseId,
  selectedIds = [],
  onSelect,
}: {
  caseId: string
  selectedIds?: string[]
  onSelect: (item: { id: string; label: string }) => void
}) {
  const [query, setQuery] = useState("")
  const options = useAttachmentOptions(caseId, "evidence", query, true)
  return (
    <div className="overflow-hidden rounded-lg border border-border">
      <div className="border-b border-border p-2">
        <Input
          className="h-8 text-xs"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search evidence by filename…"
          aria-label="Search evidence"
        />
      </div>
      <div className="max-h-48 overflow-y-auto p-1.5">
        {options.isLoading ? (
          <div className="flex justify-center py-5">
            <Loader2 className="size-4 animate-spin text-muted-foreground" />
          </div>
        ) : options.data?.items.length ? (
          options.data.items.map((item) => (
            <div
              key={item.target_id}
              className="flex items-center gap-2 rounded-md px-2 py-2 hover:bg-muted/50"
            >
              <FileImage className="size-4 shrink-0 text-muted-foreground" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-xs font-medium">{item.label}</p>
                {item.description ? (
                  <p className="truncate text-[10px] text-muted-foreground">
                    {item.description}
                  </p>
                ) : null}
              </div>
              <Button
                size="sm"
                variant="ghost"
                className="h-7 text-[11px]"
                disabled={selectedIds.includes(item.target_id)}
                onClick={() =>
                  onSelect({ id: item.target_id, label: item.label })
                }
              >
                <Plus className="size-3" />{" "}
                {selectedIds.includes(item.target_id) ? "Added" : "Add"}
              </Button>
            </div>
          ))
        ) : (
          <p className="py-6 text-center text-xs text-muted-foreground">
            No matching evidence
          </p>
        )}
      </div>
    </div>
  )
}
