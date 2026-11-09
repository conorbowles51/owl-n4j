import { useEffect } from "react"
import { create } from "zustand"

/**
 * The document open on screen, for the step history (lx-guide I, J): the shared document viewer reports which file
 * and page it shows, and a step that returns to a document asks for it here. One small store; the viewer reads it.
 */
export interface DocumentStep {
  evidenceId: string
  name?: string | null
  page: number
  pages?: number | null
}

interface DocumentStepState {
  open: DocumentStep | null
  /** A document a restored step wants open, at its page; the history layer opens it and the viewer jumps there. */
  wanted: DocumentStep | null
  report: (doc: DocumentStep | null) => void
  request: (doc: DocumentStep | null) => void
}

export const useDocumentStep = create<DocumentStepState>((set) => ({
  open: null,
  wanted: null,
  report: (doc) => set({ open: doc }),
  request: (doc) => set({ wanted: doc }),
}))

/** The viewer's one-line hook: tells the history which document and page is on screen while it is open. */
export function useReportDocument(doc: DocumentStep | null) {
  const key = doc ? `${doc.evidenceId}:${doc.page}:${doc.pages ?? ""}:${doc.name ?? ""}` : ""
  useEffect(() => {
    useDocumentStep.getState().report(doc)
    return () => {
      if (useDocumentStep.getState().open?.evidenceId === doc?.evidenceId) useDocumentStep.getState().report(null)
    }
    // the key holds every field that matters
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])
}
