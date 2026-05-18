import { useEffect, useMemo, useState } from "react"
import { Search, X } from "lucide-react"
import { useQuery } from "@tanstack/react-query"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

import { evidenceTagsAPI } from "../../api"
import { useCellebriteFiles, useCellebriteFilesTree } from "../../hooks/use-cellebrite"
import type { CellebriteRecord, PhoneReport, RailSelection } from "../../types"
import { compactNumber } from "../shared/cellebrite-format"
import { FileBulkActionsBar } from "./FileBulkActionsBar"
import { FileDetailPanel } from "./FileDetailPanel"
import { FilesList } from "./FilesList"
import { FilesTree } from "./FilesTree"
import {
  type CellebriteFileRecord,
  type FileTreeSelection,
  type FilesGroupBy,
  type FilesLayout,
  fileId,
  fileName,
  selectedFilterValue,
} from "./filesUtils"

export function FilesTab({
  active,
  caseId,
  reportKeys,
  reports,
  query,
  onSelect,
}: {
  active: boolean
  caseId: string
  reportKeys: string[] | null
  reports: PhoneReport[]
  query: string
  onSelect: (selection: RailSelection) => void
}) {
  const [groupBy, setGroupBy] = useState<FilesGroupBy>("category")
  const [activeNode, setActiveNode] = useState<FileTreeSelection | null>(null)
  const [search, setSearch] = useState("")
  const [onlyRelevant, setOnlyRelevant] = useState(false)
  const [captureAfter, setCaptureAfter] = useState("")
  const [captureBefore, setCaptureBefore] = useState("")
  const [hasGeotag, setHasGeotag] = useState<boolean | null>(null)
  const [layout, setLayout] = useState<FilesLayout>("grid")
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [activeFile, setActiveFile] = useState<CellebriteFileRecord | null>(null)
  const debouncedSearch = useDebouncedValue(search || query, 300)

  const treeQuery = useCellebriteFilesTree(caseId, { reportKeys, groupBy }, active)
  const filesQuery = useCellebriteFiles(
    caseId,
    {
      reportKeys,
      category: selectedFilterValue(activeNode, "category") || null,
      parentLabel: selectedFilterValue(activeNode, "parent_label") || null,
      sourceApp: selectedFilterValue(activeNode, "source_app") || null,
      devicePath: selectedFilterValue(activeNode, "device_path") || null,
      search: debouncedSearch || null,
      onlyRelevant,
      captureAfter: captureAfter || null,
      captureBefore: captureBefore || null,
      hasGeotag,
      limit: 500,
    },
    active
  )
  const tagsQuery = useQuery({
    queryKey: ["evidence-tags", caseId],
    queryFn: () => evidenceTagsAPI.getCaseTags(caseId),
    enabled: active && Boolean(caseId),
  })
  const files = useMemo(
    () => ((filesQuery.data?.files ?? []) as CellebriteRecord[]) as CellebriteFileRecord[],
    [filesQuery.data?.files]
  )
  const total = filesQuery.data?.total ?? files.length
  const caseTags = tagsQuery.data?.tags ?? []

  function cycleGeotag() {
    setHasGeotag((current) => (current === null ? true : current ? false : null))
  }

  function toggleSelect(id: string) {
    setSelectedIds((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function selectRange(startIndex: number, endIndex: number) {
    const start = Math.min(startIndex, endIndex)
    const end = Math.max(startIndex, endIndex)
    setSelectedIds((current) => {
      const next = new Set(current)
      for (let index = start; index <= end; index += 1) {
        if (files[index]) next.add(fileId(files[index]))
      }
      return next
    })
  }

  function openFile(file: CellebriteFileRecord) {
    setActiveFile(file)
    onSelect({
      id: fileId(file),
      kind: "file",
      title: fileName(file),
      payload: file,
    })
  }

  function refresh() {
    void filesQuery.refetch()
    void tagsQuery.refetch()
  }

  function updateActiveFile(file: CellebriteFileRecord) {
    setActiveFile(file)
    refresh()
  }

  const hasFilters = Boolean(search || onlyRelevant || captureAfter || captureBefore || hasGeotag !== null || activeNode?.key)

  return (
    <section className="flex h-full min-h-0 flex-col overflow-hidden bg-background">
      <div className="flex shrink-0 items-center gap-2 border-b border-border bg-muted/30 px-3 py-2">
        <div className="relative min-w-64 flex-1 max-w-md">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search filename..."
            className="h-8 pl-8 text-xs"
          />
        </div>
        <label className="flex h-8 cursor-pointer items-center gap-1 rounded-md border border-border bg-card px-2 text-xs text-muted-foreground hover:bg-muted">
          <input
            type="checkbox"
            checked={onlyRelevant}
            onChange={(event) => setOnlyRelevant(event.target.checked)}
            className="size-3 accent-amber-500"
          />
          Only relevant
        </label>
        <span className="text-xs text-muted-foreground">Taken</span>
        <Input type="date" value={captureAfter} onChange={(event) => setCaptureAfter(event.target.value)} className="h-8 w-36 text-xs" />
        <span className="text-xs text-muted-foreground">to</span>
        <Input type="date" value={captureBefore} onChange={(event) => setCaptureBefore(event.target.value)} className="h-8 w-36 text-xs" />
        <Button
          type="button"
          variant={hasGeotag === null ? "outline" : "secondary"}
          size="sm"
          className="h-8 px-2 text-xs"
          onClick={cycleGeotag}
          title="Cycle geotag filter"
        >
          {hasGeotag === true ? "Geotagged" : hasGeotag === false ? "No geotag" : "Any geotag"}
        </Button>
        <div className="flex-1" />
        <Badge variant="slate">{compactNumber(total)} files</Badge>
        {hasFilters ? (
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            title="Clear filters"
            onClick={() => {
              setSearch("")
              setOnlyRelevant(false)
              setCaptureAfter("")
              setCaptureBefore("")
              setHasGeotag(null)
              setActiveNode(null)
            }}
          >
            <X className="size-4" />
          </Button>
        ) : null}
      </div>
      <FileBulkActionsBar
        caseId={caseId}
        selectedIds={selectedIds}
        caseTags={caseTags}
        onClear={() => setSelectedIds(new Set())}
        onChanged={refresh}
      />
      <div className="flex min-h-0 flex-1">
        <FilesTree
          tree={treeQuery.data}
          groupBy={groupBy}
          selectedKey={activeNode?.key ?? null}
          loading={treeQuery.isLoading}
          onGroupByChange={(next) => {
            setGroupBy(next)
            setActiveNode(null)
          }}
          onSelect={setActiveNode}
        />
        <FilesList
          files={files}
          reports={reports}
          total={total}
          loading={filesQuery.isLoading}
          selectedIds={selectedIds}
          layout={layout}
          onLayoutChange={setLayout}
          onToggleSelect={toggleSelect}
          onRangeSelect={selectRange}
          onOpen={openFile}
        />
        <FileDetailPanel
          caseId={caseId}
          file={activeFile}
          caseTags={caseTags}
          onClose={() => setActiveFile(null)}
          onFileChanged={updateActiveFile}
        />
      </div>
    </section>
  )
}

function useDebouncedValue(value: string, delayMs: number) {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timeout = window.setTimeout(() => setDebounced(value), delayMs)
    return () => window.clearTimeout(timeout)
  }, [delayMs, value])
  return debounced
}
