import type { ReactNode } from "react"
import { Markdown } from "@/components/ui/markdown"
import { CitationProvider, PAGE_NOT_GIVEN } from "@/components/citations/citations"
import type { AgentCitationCheck } from "../types"

/** Shown when a citation names a file but no page (the shared citation renderer's words). */
export const NO_CITATION_PAGE = PAGE_NOT_GIVEN

/** Citations in agent answers and report sections open with the shared citation rules; a phone record opens in its
 * panel beside the answer. */
export function AgentCitationProvider({ caseId, children }: { caseId: string; children: ReactNode }) {
  return (
    <CitationProvider caseId={caseId} recordPanel>
      {children}
    </CitationProvider>
  )
}

/** Markdown for agent answers and report sections, with citations checked against the case. */
export function AgentMarkdown({ content, className }: { content: string; className?: string }) {
  return <Markdown content={content} className={className} />
}

const plural = (n: number, one: string, many: string) => `${n.toLocaleString("en-US")} ${n === 1 ? one : many}`

/** The answer check under an agent answer: how many citations were checked against the case, and how many failed. */
export function CitationCheckLine({ check }: { check: AgentCitationCheck }) {
  if (check.available === false)
    return (
      <p role="status" className="mt-2 text-xs text-muted-foreground" data-testid="citation-check">
        {check.reason ?? "The citations in this answer could not be checked."}
      </p>
    )
  const total = check.total ?? 0
  if (!total) return null
  const missing = check.not_in_case ?? 0
  const ambiguous = check.ambiguous ?? 0
  const parts = [
    missing ? `${plural(missing, "is", "are")} not in this case and ${missing === 1 ? "is" : "are"} marked` : null,
    ambiguous ? `${plural(ambiguous, "names a file", "name files")} several files share; choose one when opening` : null,
    check.page_not_given ? `${plural(check.page_not_given, "document citation gives", "document citations give")} no page` : null,
  ].filter(Boolean)
  return (
    <p
      role="status"
      className={missing ? "mt-2 text-xs text-destructive" : "mt-2 text-xs text-muted-foreground"}
      data-testid="citation-check"
    >
      {`${plural(total, "citation", "citations")} checked against this case: ${(check.ok ?? 0).toLocaleString("en-US")} open${parts.length ? `; ${parts.join("; ")}` : ""}.`}
    </p>
  )
}
