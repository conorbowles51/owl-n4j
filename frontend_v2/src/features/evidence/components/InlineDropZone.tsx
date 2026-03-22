import { useCallback } from "react"
import { Upload } from "lucide-react"
import { motion, AnimatePresence } from "framer-motion"
import { useUploadToFolder } from "../hooks/use-upload-to-folder"
import { toast } from "sonner"

interface InlineDropZoneProps {
  caseId: string
  folderId: string | null
  folderName: string
  onDropComplete: () => void
}

export function InlineDropZone({
  caseId,
  folderId,
  folderName,
  onDropComplete,
}: InlineDropZoneProps) {
  const uploadMutation = useUploadToFolder(caseId)

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      e.stopPropagation()

      const files = Array.from(e.dataTransfer.files)
      if (files.length === 0) {
        onDropComplete()
        return
      }

      uploadMutation.mutate(
        { files, folderId },
        {
          onSuccess: () => {
            toast.success(
              `Uploaded ${files.length} file${files.length !== 1 ? "s" : ""} to ${folderName}`
            )
            onDropComplete()
          },
          onError: (err) => {
            toast.error(err.message)
            onDropComplete()
          },
        }
      )
    },
    [caseId, folderId, folderName, onDropComplete, uploadMutation]
  )

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = "copy"
  }, [])

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.15 }}
        className="absolute inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm"
        onDrop={handleDrop}
        onDragOver={handleDragOver}
      >
        <div className="flex flex-col items-center gap-4 rounded-xl border-2 border-dashed border-amber-500/50 bg-amber-500/5 px-12 py-10">
          <div className="rounded-full bg-amber-500/10 p-4">
            <Upload className="size-8 text-amber-500" />
          </div>
          <div className="text-center">
            <p className="text-sm font-medium text-foreground">
              Drop files to upload
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              to {folderName}
            </p>
          </div>
        </div>
      </motion.div>
    </AnimatePresence>
  )
}
