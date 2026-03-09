import { useState, useCallback } from "react"
import { Upload, FolderUp, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/cn"
import { useUploadEvidence } from "../hooks/use-evidence"

interface EvidenceUploaderProps {
  caseId: string
  onComplete?: () => void
}

export function EvidenceUploader({ caseId, onComplete }: EvidenceUploaderProps) {
  const uploadMutation = useUploadEvidence(caseId)
  const [isDragging, setIsDragging] = useState(false)
  const [pendingFiles, setPendingFiles] = useState<File[]>([])

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(true)
  }, [])

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
  }, [])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    const files = Array.from(e.dataTransfer.files)
    if (files.length) setPendingFiles((prev) => [...prev, ...files])
  }, [])

  const handleFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files
      if (files) setPendingFiles((prev) => [...prev, ...Array.from(files)])
      e.target.value = ""
    },
    []
  )

  const handleFolderSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files
      if (files) setPendingFiles((prev) => [...prev, ...Array.from(files)])
      e.target.value = ""
    },
    []
  )

  const removeFile = (index: number) => {
    setPendingFiles((prev) => prev.filter((_, i) => i !== index))
  }

  const handleUpload = () => {
    if (pendingFiles.length === 0) return
    uploadMutation.mutate(pendingFiles, {
      onSuccess: () => {
        setPendingFiles([])
        onComplete?.()
      },
    })
  }

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  return (
    <div className="space-y-3">
      {/* Drop zone */}
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={cn(
          "flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-8 transition-colors",
          isDragging
            ? "border-amber-500 bg-amber-500/5"
            : "border-border hover:border-muted-foreground/50"
        )}
      >
        <Upload className="size-8 text-muted-foreground" />
        <p className="text-sm text-muted-foreground">
          Drag & drop files here, or
        </p>
        <div className="flex gap-2">
          <label>
            <Button variant="outline" size="sm" asChild>
              <span>
                <Upload className="size-3.5" />
                Files
              </span>
            </Button>
            <input
              type="file"
              multiple
              className="hidden"
              onChange={handleFileSelect}
            />
          </label>
          <label>
            <Button variant="outline" size="sm" asChild>
              <span>
                <FolderUp className="size-3.5" />
                Folder
              </span>
            </Button>
            <input
              type="file"
              className="hidden"
              onChange={handleFolderSelect}
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              {...({ webkitdirectory: "", directory: "" } as React.InputHTMLAttributes<HTMLInputElement>)}
              multiple
            />
          </label>
        </div>
      </div>

      {/* Pending files list */}
      {pendingFiles.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <p className="text-xs font-medium text-foreground">
              {pendingFiles.length} file{pendingFiles.length !== 1 ? "s" : ""} ready
            </p>
            <div className="flex gap-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setPendingFiles([])}
              >
                Clear
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={handleUpload}
                disabled={uploadMutation.isPending}
              >
                {uploadMutation.isPending ? "Uploading..." : "Upload all"}
              </Button>
            </div>
          </div>
          <div className="max-h-40 overflow-auto rounded-md border">
            {pendingFiles.map((file, i) => (
              <div
                key={`${file.name}-${i}`}
                className="flex items-center justify-between border-b border-border px-3 py-1.5 last:border-0"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs text-foreground">{file.name}</p>
                  <p className="text-[10px] text-muted-foreground">
                    {formatSize(file.size)}
                  </p>
                </div>
                <button
                  onClick={() => removeFile(i)}
                  className="ml-2 text-muted-foreground hover:text-foreground"
                >
                  <X className="size-3" />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
