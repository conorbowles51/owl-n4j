import { createContext, useContext, useState, type ReactNode } from "react"
import { toast } from "sonner"
import { DocumentViewer } from "@/components/ui/document-viewer"
import { Markdown } from "@/components/ui/markdown"
import { evidenceAPI } from "@/features/evidence/api"
import { PhoneRecordPanel } from "@/features/phones/components/RecordPanel"

export const NO_CITATION_PAGE = "No page was given for this citation."

type OpenDocument = (filename: string, page?: number) => void

type OpenRecord = (recordUid: string, fieldPath: string | null) => void

const AgentDocumentOpener = createContext<OpenDocument | undefined>(undefined)
const AgentRecordOpener = createContext<OpenRecord | undefined>(undefined)

/** Opens doc:// citations in agent answers and reports the way the chat does: the file by name in this case, at the
 * cited page, or at its start with a note when the citation gives no page. */
export function AgentCitationProvider({ caseId, children }: { caseId: string; children: ReactNode }) {
  const [viewer, setViewer] = useState<{
    evidenceId: string
    url: string
    name: string
    page?: number
  } | null>(null)

  const openDocument: OpenDocument = async (filename, page) => {
    try {
      const result = await evidenceAPI.findByFilename(filename, caseId)
      if (!result.found || !result.evidence_id) {
        toast.error(`Source file not found: ${filename}`)
        return
      }
      setViewer({
        evidenceId: result.evidence_id,
        url: evidenceAPI.getFileUrl(result.evidence_id),
        name: filename,
        page,
      })
    } catch {
      toast.error("Failed to load source file")
    }
  }

  const [record, setRecord] = useState<string | null>(null)
  const openRecord: OpenRecord = (recordUid) => setRecord(recordUid)

  return (
    <AgentDocumentOpener.Provider value={openDocument}>
      <AgentRecordOpener.Provider value={openRecord}>
      {children}
      {record && <PhoneRecordPanel caseId={caseId} recordUid={record} onClose={() => setRecord(null)} />}
      <DocumentViewer
        caseId={caseId}
        evidenceId={viewer?.evidenceId}
        open={!!viewer}
        onOpenChange={(open) => {
          if (!open) setViewer(null)
        }}
        documentUrl={viewer?.url}
        documentName={viewer?.name}
        initialPage={viewer?.page ?? 1}
        notice={viewer && viewer.page === undefined ? NO_CITATION_PAGE : undefined}
      />
      </AgentRecordOpener.Provider>
    </AgentDocumentOpener.Provider>
  )
}

/** Markdown for agent answers and report sections, with document citations that open. */
export function AgentMarkdown({ content, className }: { content: string; className?: string }) {
  const openDocument = useContext(AgentDocumentOpener)
  const openRecord = useContext(AgentRecordOpener)
  return <Markdown content={content} className={className} onOpenDocument={openDocument} onOpenRecord={openRecord} />
}
