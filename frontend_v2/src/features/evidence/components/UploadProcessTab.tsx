import { useState } from "react"
import { Wand2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { EvidenceUploader } from "./EvidenceUploader"
import type { UploadResponse } from "../api"
import { FolderProfileWizard } from "./FolderProfileWizard"
import { useEvidenceStore } from "../evidence.store"
import { toast } from "sonner"

interface UploadProcessTabProps {
  caseId: string
}

export function UploadProcessTab({ caseId }: UploadProcessTabProps) {
  const setActiveTab = useEvidenceStore((s) => s.setActiveTab)
  const [wizardFolderPath, setWizardFolderPath] = useState("")

  return (
    <div className="flex flex-col gap-6 p-6">
      <div>
        <h2 className="mb-1 text-sm font-semibold text-foreground">Upload Files</h2>
        <p className="mb-4 text-xs text-muted-foreground">
          Drag and drop files or folders, or click to browse. Files are processed automatically after upload.
        </p>
        <EvidenceUploader
          caseId={caseId}
          onComplete={(result: UploadResponse) => {
            if (result.job_ids?.length) {
              // Evidence engine: files uploaded and processing started automatically
              toast.success(
                `${result.files?.length ?? result.job_ids.length} file${(result.files?.length ?? result.job_ids.length) !== 1 ? "s" : ""} uploaded — processing started`
              )
              setActiveTab("activity")
            } else if (result.files) {
              toast.success(`${result.files.length} file${result.files.length !== 1 ? "s" : ""} uploaded`)
              setActiveTab("files")
            } else if (result.task_id || result.task_ids) {
              toast.info(result.message ?? "Upload started in background")
              setActiveTab("activity")
            }
          }}
        />
      </div>

      {/* Folder Profile Wizard shortcut */}
      <div className="rounded-lg border border-border bg-card p-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-foreground">Folder Profile Wizard</p>
            <p className="text-xs text-muted-foreground">
              Configure custom processing rules for a specific folder
            </p>
          </div>
          <form
            className="flex items-center gap-2"
            onSubmit={(e) => {
              e.preventDefault()
              const fd = new FormData(e.currentTarget)
              const path = (fd.get("folderPath") as string)?.trim()
              if (path) setWizardFolderPath(path)
              else toast.error("Enter a folder path")
            }}
          >
            <Input
              name="folderPath"
              placeholder="e.g., evidence/wiretaps/batch-01"
              className="h-8 w-64"
            />
            <Button variant="outline" size="sm" type="submit">
              <Wand2 className="size-3.5" />
              Configure
            </Button>
          </form>
        </div>
      </div>

      {wizardFolderPath && (
        <FolderProfileWizard
          open={!!wizardFolderPath}
          onOpenChange={(open) => {
            if (!open) setWizardFolderPath("")
          }}
          caseId={caseId}
          folderPath={wizardFolderPath}
          onComplete={(config) => {
            toast.success("Folder profile configuration saved")
            console.log("Folder profile config:", config)
          }}
        />
      )}
    </div>
  )
}
