import { useRef } from "react"
import { LayoutGrid, List, Loader2 } from "lucide-react"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/cn"

import type { PhoneReport } from "../../types"
import { compactNumber } from "../shared/cellebrite-format"
import { SmallEmpty } from "../shared/SmallEmpty"
import { FileThumbnail } from "./FileThumbnail"
import type { CellebriteFileRecord, FilesLayout } from "./filesUtils"
import { fileId } from "./filesUtils"

export function FilesList({
  files,
  reports,
  total,
  loading,
  selectedIds,
  layout,
  onLayoutChange,
  onToggleSelect,
  onRangeSelect,
  onOpen,
}: {
  files: CellebriteFileRecord[]
  reports: PhoneReport[]
  total: number
  loading: boolean
  selectedIds: Set<string>
  layout: FilesLayout
  onLayoutChange: (layout: FilesLayout) => void
  onToggleSelect: (id: string) => void
  onRangeSelect: (startIndex: number, endIndex: number) => void
  onOpen: (file: CellebriteFileRecord) => void
}) {
  const lastSelectedIndexRef = useRef<number | null>(null)

  function toggle(file: CellebriteFileRecord, index: number, shiftKey = false) {
    if (shiftKey && lastSelectedIndexRef.current !== null) {
      onRangeSelect(lastSelectedIndexRef.current, index)
    } else {
      onToggleSelect(fileId(file))
    }
    lastSelectedIndexRef.current = index
  }

  return (
    <div className="flex min-w-0 flex-1 flex-col">
      <div className="flex h-10 shrink-0 items-center justify-between border-b border-border bg-muted/20 px-3">
        <div className="text-xs text-muted-foreground">
          {loading ? "Loading..." : `${compactNumber(files.length)} of ${compactNumber(total)} files`}
          {selectedIds.size > 0 ? <span className="ml-2 font-medium text-amber-600">{compactNumber(selectedIds.size)} selected</span> : null}
        </div>
        <div className="flex items-center gap-1">
          <Button type="button" variant={layout === "grid" ? "secondary" : "ghost"} size="icon-sm" onClick={() => onLayoutChange("grid")} title="Grid view">
            <LayoutGrid className="size-3.5" />
          </Button>
          <Button type="button" variant={layout === "list" ? "secondary" : "ghost"} size="icon-sm" onClick={() => onLayoutChange("list")} title="List view">
            <List className="size-3.5" />
          </Button>
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {loading && files.length === 0 ? (
          <div className="flex h-full items-center justify-center">
            <Loader2 className="size-5 animate-spin text-muted-foreground" />
          </div>
        ) : files.length === 0 ? (
          <SmallEmpty label="No files match the current filters." />
        ) : layout === "grid" ? (
          <div className="grid gap-2 p-3" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))" }}>
            {files.map((file, index) => (
              <FileThumbnail
                key={fileId(file)}
                file={file}
                reports={reports}
                selected={selectedIds.has(fileId(file))}
                layout="grid"
                onToggleSelect={(shiftKey) => toggle(file, index, shiftKey)}
                onOpen={() => onOpen(file)}
              />
            ))}
          </div>
        ) : (
          <div className={cn(loading && "opacity-70")}>
            {files.map((file, index) => (
              <div key={fileId(file)}>
                <FileThumbnail
                  file={file}
                  reports={reports}
                  selected={selectedIds.has(fileId(file))}
                  layout="list"
                  onToggleSelect={(shiftKey) => toggle(file, index, shiftKey)}
                  onOpen={() => onOpen(file)}
                />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
