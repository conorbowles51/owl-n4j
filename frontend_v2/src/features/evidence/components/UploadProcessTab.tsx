import { useState } from "react"
import { Play, Wand2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { EvidenceUploader } from "./EvidenceUploader"
import { ProcessDialog } from "./ProcessDialog"
import { FolderProfileWizard } from "./FolderProfileWizard"
import { useEvidence } from "../hooks/use-evidence"
import { useProcessBackground } from "../hooks/use-evidence-detail"
import { useEvidenceStore } from "../evidence.store"
import { toast } from "sonner"

interface UploadProcessTabProps {
  caseId: string
}

export function UploadProcessTab({ caseId }: UploadProcessTabProps) {
  const { data: files } = useEvidence(caseId)
  const processMutation = useProcessBackground(caseId)
  const setActiveTab = useEvidenceStore((s) => s.setActiveTab)
  const [processOpen, setProcessOpen] = useState(false)
  const [wizardFolderPath, setWizardFolderPath] = useState("")

  const unprocessed = files?.filter((f) => f.status === "unprocessed") ?? []

  const handleProcessAll = () => {
    if (unprocessed.length > 0) {
      setProcessOpen(true)
    }
  }

  const handleConfirmProcess = (config: {
    profile?: string
    maxWorkers: number
    imageProvider?: string
  }) => {
    processMutation.mutate(
      {
        fileIds: unprocessed.map((f) => f.id),
        profile: config.profile,
        maxWorkers: config.maxWorkers,
        imageProvider: config.imageProvider,
      },
      {
        onSuccess: () => {
          toast.success("Processing started in background")
          setProcessOpen(false)
          setActiveTab("activity")
        },
        onError: (err) => {
          toast.error(`Failed to start processing: ${err.message}`)
        },
      }
    )
  }

  return (
    <div className="flex flex-col gap-6 p-6">
      <div>
        <h2 className="mb-1 text-sm font-semibold text-foreground">Upload Files</h2>
        <p className="mb-4 text-xs text-muted-foreground">
          Drag and drop files or folders, or click to browse
        </p>
        <EvidenceUploader caseId={caseId} />
      </div>

      {unprocessed.length > 0 && (
        <div className="rounded-lg border border-border bg-card p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-foreground">
                {unprocessed.length} unprocessed file{unprocessed.length !== 1 ? "s" : ""}
              </p>
              <p className="text-xs text-muted-foreground">
                Ready to be processed with AI entity extraction
              </p>
            </div>
            <Button variant="primary" size="sm" onClick={handleProcessAll}>
              <Play className="size-3.5" />
              Process All
            </Button>
          </div>
        </div>
      )}

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

      <ProcessDialog
        open={processOpen}
        onOpenChange={setProcessOpen}
        fileCount={unprocessed.length}
        onConfirm={handleConfirmProcess}
        isPending={processMutation.isPending}
      />

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
