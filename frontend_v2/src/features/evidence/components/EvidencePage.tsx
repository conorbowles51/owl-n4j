import { useState, useCallback } from "react"
import { useParams } from "react-router-dom"
import { Upload, RefreshCw, Trash2, Play } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { PageHeader } from "@/components/ui/page-header"
import { EmptyState } from "@/components/ui/empty-state"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { StatusIndicator } from "@/components/ui/status-indicator"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Checkbox } from "@/components/ui/checkbox"
import { useEvidence, useUploadEvidence, useProcessEvidence } from "../hooks/use-evidence"

export function EvidencePage() {
  const { id: caseId } = useParams()
  const { data: files, isLoading } = useEvidence(caseId)
  const uploadMutation = useUploadEvidence(caseId!)
  const processMutation = useProcessEvidence(caseId!)
  const [search, setSearch] = useState("")
  const [selected, setSelected] = useState<Set<string>>(new Set())

  const filtered = files?.filter((f) =>
    f.filename.toLowerCase().includes(search.toLowerCase())
  )

  const toggleSelect = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleAll = () => {
    if (selected.size === filtered?.length) {
      setSelected(new Set())
    } else {
      setSelected(new Set(filtered?.map((f) => f.id)))
    }
  }

  const handleUpload = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const fileList = e.target.files
      if (fileList) {
        uploadMutation.mutate(Array.from(fileList))
        e.target.value = ""
      }
    },
    [uploadMutation]
  )

  const handleProcess = () => {
    if (selected.size > 0) {
      processMutation.mutate({ fileIds: Array.from(selected) })
      setSelected(new Set())
    }
  }

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-border px-6 py-3">
        <PageHeader
          title="Evidence"
          actions={
            <div className="flex gap-2">
              {selected.size > 0 && (
                <>
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={handleProcess}
                    disabled={processMutation.isPending}
                  >
                    <Play className="size-3.5" />
                    Process ({selected.size})
                  </Button>
                  <Button variant="danger" size="sm">
                    <Trash2 className="size-3.5" />
                    Delete ({selected.size})
                  </Button>
                </>
              )}
              <label>
                <Button variant="outline" size="sm" asChild>
                  <span>
                    <Upload className="size-3.5" />
                    Upload
                  </span>
                </Button>
                <input
                  type="file"
                  multiple
                  className="hidden"
                  onChange={handleUpload}
                />
              </label>
            </div>
          }
        />
      </div>

      <div className="border-b border-border px-6 py-2">
        <Input
          placeholder="Filter files..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-sm"
        />
      </div>

      <div className="flex-1 overflow-auto">
        {isLoading ? (
          <div className="flex justify-center py-12">
            <LoadingSpinner />
          </div>
        ) : !filtered?.length ? (
          <EmptyState
            icon={Upload}
            title="No evidence files"
            description="Upload files to begin processing evidence"
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-8">
                  <Checkbox
                    checked={
                      selected.size > 0 &&
                      selected.size === filtered.length
                    }
                    onCheckedChange={toggleAll}
                  />
                </TableHead>
                <TableHead>Filename</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Size</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Entities</TableHead>
                <TableHead>Uploaded</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((file) => (
                <TableRow key={file.id}>
                  <TableCell>
                    <Checkbox
                      checked={selected.has(file.id)}
                      onCheckedChange={() => toggleSelect(file.id)}
                    />
                  </TableCell>
                  <TableCell className="max-w-[300px] truncate font-medium">
                    {file.filename}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {file.file_type}
                  </TableCell>
                  <TableCell className="font-mono text-xs">
                    {formatSize(file.file_size)}
                  </TableCell>
                  <TableCell>
                    <StatusIndicator status={file.status} />
                  </TableCell>
                  <TableCell className="font-mono text-xs">
                    {file.entity_count ?? "—"}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {new Date(file.uploaded_at).toLocaleDateString()}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>

      {uploadMutation.isPending && (
        <div className="flex items-center gap-2 border-t border-border px-6 py-2 text-xs text-muted-foreground">
          <RefreshCw className="size-3 animate-spin" />
          Uploading files...
        </div>
      )}
    </div>
  )
}
