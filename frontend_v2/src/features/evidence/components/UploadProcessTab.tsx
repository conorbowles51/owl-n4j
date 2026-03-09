import { useState } from "react"
import { Play } from "lucide-react"
import { Button } from "@/components/ui/button"
import { EvidenceUploader } from "./EvidenceUploader"
import { ProcessDialog } from "./ProcessDialog"
import { useEvidence } from "../hooks/use-evidence"
import { useProcessBackground } from "../hooks/use-evidence-detail"
import { toast } from "sonner"

interface UploadProcessTabProps {
  caseId: string
}

export function UploadProcessTab({ caseId }: UploadProcessTabProps) {
  const { data: files } = useEvidence(caseId)
  const processMutation = useProcessBackground(caseId)
  const [processOpen, setProcessOpen] = useState(false)

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

      <ProcessDialog
        open={processOpen}
        onOpenChange={setProcessOpen}
        fileCount={unprocessed.length}
        onConfirm={handleConfirmProcess}
        isPending={processMutation.isPending}
      />
    </div>
  )
}
