import { useEffect, useState } from "react"
import { DocumentViewer } from "@/components/ui/document-viewer"
import { evidenceAPI } from "@/features/evidence/api"
import { useDocumentStep, type DocumentStep } from "./document-step"

/**
 * A step that was on a document opens it again at its page (lx-guide I). The screen's own viewer takes the request
 * when it has that document open; otherwise, after a moment, this opens the shared viewer over the screen.
 */
export function HistoryDocument({ caseId }: { caseId: string }) {
  const wanted = useDocumentStep((s) => s.wanted)
  const [shown, setShown] = useState<DocumentStep | null>(null)
  useEffect(() => {
    if (!wanted) return
    const t = window.setTimeout(() => {
      const still = useDocumentStep.getState().wanted
      if (still && still.evidenceId === wanted.evidenceId) {
        setShown(still)
      }
    }, 1500)
    return () => window.clearTimeout(t)
  }, [wanted])
  if (!shown) return null
  return (
    <DocumentViewer
      caseId={caseId}
      evidenceId={shown.evidenceId}
      open
      onOpenChange={(open) => {
        if (!open) {
          setShown(null)
          useDocumentStep.getState().request(null)
        }
      }}
      documentUrl={evidenceAPI.getFileUrl(shown.evidenceId)}
      documentName={shown.name ?? undefined}
      initialPage={shown.page || 1}
    />
  )
}
