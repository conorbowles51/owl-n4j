import { createContext, useContext, useMemo, useState, type ReactNode } from "react"
import { QueryClientContext, useQuery } from "@tanstack/react-query"
import { Link, useParams } from "react-router-dom"
import { toast } from "sonner"
import { resolveCitations, type CitationResolution } from "@/lib/citation-check"
import { citationHrefs, parseCitation, paymentPath, type Citation } from "@/lib/citations"
import { recordPath } from "@/lib/record-links"
import { DocumentViewer } from "@/components/ui/document-viewer"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { evidenceAPI } from "@/features/evidence/api"
import { PhoneRecordPanel } from "@/features/phones/components/RecordPanel"

/** Shown when a citation names a file but no page: the file opens at its start, and says why. */
export const PAGE_NOT_GIVEN = "Page not given: this citation names the file, not a page. It opens at the start."
export const NOT_IN_CASE = "not in this case"

interface Opener {
  caseId: string
  open: (href: string, known?: CitationResolution) => Promise<void>
  recordPanel: boolean
}

const OpenerContext = createContext<Opener | null>(null)
const ResolutionContext = createContext<ReadonlyMap<string, CitationResolution> | null>(null)

interface ViewerState {
  evidenceId: string
  name: string
  page?: number
}

/**
 * Opens every citation the same way, wherever it is rendered: a document at its cited page (or at its start, saying
 * the page was not given), a filename several files share as a choice of those files, a ledger row on the Financial
 * page at its statement page, a phone record in its panel (recordPanel) or on its page.
 */
export function CitationProvider({
  caseId,
  recordPanel = false,
  children,
}: {
  caseId: string
  recordPanel?: boolean
  children: ReactNode
}) {
  const [viewer, setViewer] = useState<ViewerState | null>(null)
  const [choice, setChoice] = useState<CitationResolution | null>(null)
  const [record, setRecord] = useState<string | null>(null)

  const showDocument = (resolution: CitationResolution, evidenceId: string, name?: string) =>
    setViewer({ evidenceId, name: name || resolution.filename || "Source file", page: resolution.page ?? undefined })

  const open = async (href: string, known?: CitationResolution) => {
    const citation = parseCitation(href)
    if (!citation) return
    let resolution = known
    if (!resolution) {
      try {
        resolution = (await resolveCitations(caseId, [href])).get(href)
      } catch {
        toast.error("This citation could not be checked against the case. Try again.")
        return
      }
    }
    if (!resolution || resolution.status === "not_in_case") {
      toast.error(`This citation is ${NOT_IN_CASE}.`)
      return
    }
    if (resolution.status === "ambiguous") {
      setChoice(resolution)
      return
    }
    if (citation.scheme === "doc" && resolution.evidence_file_id)
      showDocument(resolution, resolution.evidence_file_id)
    else if (citation.scheme === "txn")
      window.open(paymentPath(caseId, citation.target), "_blank", "noopener")
    else if (citation.scheme === "rec") {
      if (recordPanel) setRecord(citation.target)
      else window.open(recordPath(caseId, citation.target, citation.field), "_blank", "noopener")
    }
  }

  const opener: Opener = { caseId, open, recordPanel }

  return (
    <OpenerContext.Provider value={opener}>
      {children}
      {record && <PhoneRecordPanel caseId={caseId} recordUid={record} onClose={() => setRecord(null)} />}
      <Dialog open={!!choice} onOpenChange={(next) => !next && setChoice(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Choose the file this citation means</DialogTitle>
            <DialogDescription>
              {choice?.reason ?? "Several files in this case have this name."} Loupe does not pick one for you.
            </DialogDescription>
          </DialogHeader>
          <ul className="space-y-1" aria-label="Files with this name">
            {choice?.candidates?.map((candidate) => (
              <li key={candidate.evidence_file_id}>
                <button
                  type="button"
                  className="w-full rounded-md border px-3 py-2 text-left text-sm hover:bg-muted"
                  onClick={() => {
                    const picked = choice
                    setChoice(null)
                    showDocument(picked, candidate.evidence_file_id, candidate.filename)
                  }}
                >
                  <span className="font-medium">{candidate.filename}</span>
                  <span className="block text-xs text-muted-foreground">
                    {candidate.uploaded_at ? `Uploaded ${new Date(candidate.uploaded_at).toLocaleString("en-GB")}` : "Upload time not recorded"}
                    {candidate.size ? ` · ${candidate.size.toLocaleString("en-GB")} bytes` : ""}
                    {choice?.page ? ` · opens at page ${choice.page}` : ""}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </DialogContent>
      </Dialog>
      <DocumentViewer
        caseId={caseId}
        evidenceId={viewer?.evidenceId}
        open={!!viewer}
        onOpenChange={(next) => {
          if (!next) setViewer(null)
        }}
        documentUrl={viewer ? evidenceAPI.getFileUrl(viewer.evidenceId) : undefined}
        documentName={viewer?.name}
        initialPage={viewer?.page ?? 1}
        notice={viewer && viewer.page === undefined ? PAGE_NOT_GIVEN : undefined}
      />
    </OpenerContext.Provider>
  )
}

/** The citations of one piece of Markdown, checked against the case in one request. */
export function CitationScope({ content, children }: { content: string; children: ReactNode }) {
  const opener = useContext(OpenerContext)
  const client = useContext(QueryClientContext)
  // Without a case or a query client (an isolated render) citations still open on click, checked then.
  if (!opener || !client) return <>{children}</>
  return <CheckedScope caseId={opener.caseId} content={content}>{children}</CheckedScope>
}

function CheckedScope({ caseId, content, children }: { caseId: string; content: string; children: ReactNode }) {
  const hrefs = useMemo(() => citationHrefs(content), [content])
  const query = useQuery({
    queryKey: ["citations", caseId, hrefs],
    enabled: !!caseId && hrefs.length > 0,
    staleTime: 60_000,
    retry: false,
    queryFn: ({ signal }) => resolveCitations(caseId, hrefs, signal),
  })
  return <ResolutionContext.Provider value={query.data ?? null}>{children}</ResolutionContext.Provider>
}

/** Markdown that renders citations needs a provider; one is made from the route's case when none encloses it. */
export function WithCitations({ children }: { children: ReactNode }) {
  const opener = useContext(OpenerContext)
  const { id: routeCaseId } = useParams()
  if (opener || !routeCaseId) return <>{children}</>
  return <CitationProvider caseId={routeCaseId}>{children}</CitationProvider>
}

const LINK = "text-blue-500 underline hover:text-blue-600"

/** One citation in rendered Markdown. A citation whose target is not in the case is never a link. */
export function CitationLink({
  citation,
  children,
  className = LINK,
  label,
  title,
}: {
  citation: Citation
  children: ReactNode
  className?: string
  /** replaces the children as the visible text (numbered summary sources) */
  label?: ReactNode
  title?: string
}) {
  const opener = useContext(OpenerContext)
  const resolutions = useContext(ResolutionContext)
  const resolution = resolutions?.get(citation.href)
  if (resolution?.status === "not_in_case" || (citation.scheme === "txn" && citation.legacy && opener &&
      citation.linkedCaseId && citation.linkedCaseId !== opener.caseId.toLowerCase()))
    return (
      <span className="text-muted-foreground" title={resolution?.reason ?? "Not in this case."} data-citation-status="not_in_case">
        {label ?? children}{" "}
        <span className="rounded-sm bg-muted px-1 text-[10px] font-medium uppercase tracking-wide">{NOT_IN_CASE}</span>
      </span>
    )
  if (!opener) return <span>{label ?? children}</span>
  if (citation.scheme === "rec" && !opener.recordPanel)
    return (
      <Link to={recordPath(opener.caseId, citation.target, citation.field)} className={className} title={title}>
        {label ?? children}
      </Link>
    )
  if (citation.scheme === "txn")
    return (
      <a
        href={paymentPath(opener.caseId, citation.target)}
        target="_blank"
        rel="noopener noreferrer"
        className={className}
        title={title ?? "Opens this payment on the Financial page, at its statement page"}
        data-citation-scheme="txn"
      >
        {label ?? children}
      </a>
    )
  return (
    <button
      type="button"
      className={className}
      title={title}
      aria-label={typeof label === "string" && title ? `Open source ${label}: ${title}` : undefined}
      data-citation-scheme={citation.scheme}
      data-citation-status={resolution?.status}
      onClick={() => void opener.open(citation.href, resolution)}
    >
      {label ?? children}
      {resolution?.status === "ambiguous" && (
        <span className="ml-1 text-[10px] text-muted-foreground no-underline">(choose file)</span>
      )}
    </button>
  )
}
