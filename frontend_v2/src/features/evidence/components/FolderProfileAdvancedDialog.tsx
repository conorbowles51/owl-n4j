import { useState, useEffect } from "react"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { FileText, Settings } from "lucide-react"
import { evidenceAPI } from "../api"
import { toast } from "sonner"

const FILE_ROLES = [
  { value: "document", label: "Document" },
  { value: "audio", label: "Audio" },
  { value: "metadata", label: "Metadata" },
  { value: "interpretation", label: "Interpretation" },
  { value: "ignore", label: "Ignore" },
]

interface FileConfig {
  filename: string
  role: string
  transcribe?: boolean
  translate?: boolean
  sourceLanguage?: string
  targetLanguage?: string
}

interface FolderProfileAdvancedDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  caseId: string
  folderPath: string
  onSaved?: (config: Record<string, unknown>) => void
}

export function FolderProfileAdvancedDialog({
  open,
  onOpenChange,
  caseId,
  folderPath,
  onSaved,
}: FolderProfileAdvancedDialogProps) {
  const [files, setFiles] = useState<FileConfig[]>([])
  const [loading, setLoading] = useState(false)
  const [jsonPreview, setJsonPreview] = useState("")

  useEffect(() => {
    if (open && folderPath) {
      setLoading(true)
      evidenceAPI
        .listFolderFiles(caseId, folderPath)
        .then((res) => {
          setFiles(
            (res.files ?? []).map((f: string) => ({
              filename: f,
              role: "document",
            }))
          )
        })
        .catch(() => toast.error("Failed to list folder files"))
        .finally(() => setLoading(false))
    }
  }, [open, caseId, folderPath])

  // Build JSON preview
  useEffect(() => {
    const config = {
      type: "special",
      file_rules: files
        .filter((f) => f.role !== "ignore")
        .map((f) => {
          const rule: Record<string, unknown> = {
            pattern: f.filename,
            role: f.role,
          }
          if (f.role === "audio") {
            rule.transcribe = f.transcribe ?? true
            rule.translate = f.translate ?? false
            if (f.sourceLanguage) rule.source_language = f.sourceLanguage
            if (f.targetLanguage) rule.target_language = f.targetLanguage
          }
          return rule
        }),
    }
    setJsonPreview(JSON.stringify(config, null, 2))
  }, [files])

  const updateFile = (index: number, updates: Partial<FileConfig>) => {
    setFiles((prev) => prev.map((f, i) => (i === index ? { ...f, ...updates } : f)))
  }

  const handleSave = () => {
    try {
      const config = JSON.parse(jsonPreview)
      onSaved?.(config)
      onOpenChange(false)
    } catch {
      toast.error("Invalid JSON configuration")
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[85vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Settings className="size-4" />
            Advanced Folder Configuration
          </DialogTitle>
        </DialogHeader>

        {loading ? (
          <div className="flex justify-center py-12">
            <LoadingSpinner />
          </div>
        ) : (
          <div className="flex-1 overflow-auto space-y-4">
            <p className="text-xs text-muted-foreground">
              Configure how each file in{" "}
              <span className="font-mono text-foreground">{folderPath}</span> should be processed.
            </p>

            <div className="space-y-2">
              {files.map((file, i) => (
                <div
                  key={file.filename}
                  className="flex items-start gap-3 rounded-md border border-border p-3"
                >
                  <FileText className="mt-1 size-3.5 text-muted-foreground" />
                  <div className="min-w-0 flex-1 space-y-2">
                    <p className="truncate text-xs font-medium text-foreground">
                      {file.filename}
                    </p>
                    <Select
                      value={file.role}
                      onValueChange={(v) => updateFile(i, { role: v })}
                    >
                      <SelectTrigger className="h-7 text-xs">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {FILE_ROLES.map((r) => (
                          <SelectItem key={r.value} value={r.value}>
                            {r.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>

                    {file.role === "audio" && (
                      <div className="flex gap-2 text-xs">
                        <label className="flex items-center gap-1">
                          <input
                            type="checkbox"
                            checked={file.transcribe ?? true}
                            onChange={(e) => updateFile(i, { transcribe: e.target.checked })}
                          />
                          Transcribe
                        </label>
                        <label className="flex items-center gap-1">
                          <input
                            type="checkbox"
                            checked={file.translate ?? false}
                            onChange={(e) => updateFile(i, { translate: e.target.checked })}
                          />
                          Translate
                        </label>
                      </div>
                    )}
                  </div>
                  <Badge variant="slate" className="shrink-0 text-[10px]">
                    {file.role}
                  </Badge>
                </div>
              ))}
            </div>

            <div>
              <label className="mb-1 block text-xs font-medium">JSON Preview</label>
              <Textarea
                value={jsonPreview}
                onChange={(e) => setJsonPreview(e.target.value)}
                className="min-h-[150px] font-mono text-xs"
              />
            </div>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button variant="primary" onClick={handleSave}>
            Save Configuration
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
