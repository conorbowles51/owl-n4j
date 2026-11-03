import { useState } from "react"
import { useMutation } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { citationHref } from "../lib/judgements"

/**
 * The review of a case agent's proposal. Each cited source opens in a new tab and the opening is recorded; Accept
 * stays disabled until at least one cited source has been opened by this person. Reject asks why. The proposal says
 * which model made it and for whom, so a reader never takes it for a person's work.
 */
export function ProposalReview({
  caseId,
  citations,
  citationLabels = {},
  opened: openedAtStart = [],
  model,
  forName,
  why,
  canEdit,
  acceptLabel = "Accept",
  acceptExtra,
  acceptBlocked,
  onOpened,
  onAccept,
  onReject,
}: {
  caseId: string
  citations: string[]
  citationLabels?: Record<string, string | null | undefined>
  opened?: string[]
  model?: string | null
  forName?: string | null
  why?: string | null
  canEdit: boolean
  acceptLabel?: string
  /** Extra fields shown above Accept (a lead card's due date). */
  acceptExtra?: React.ReactNode
  /** Why Accept is not yet possible apart from the source rule (e.g. "Set a due date"). */
  acceptBlocked?: string | null
  onOpened: (citation: string) => Promise<{ opened: string[] }>
  onAccept: () => Promise<unknown>
  onReject: (reason: string) => Promise<unknown>
}) {
  const [opened, setOpened] = useState<string[]>(openedAtStart)
  const [rejecting, setRejecting] = useState(false)
  const [reason, setReason] = useState("")
  const open = useMutation({
    mutationFn: onOpened,
    onSuccess: (data) => setOpened(data.opened),
  })
  const accept = useMutation({ mutationFn: onAccept })
  const reject = useMutation({ mutationFn: () => onReject(reason.trim()) })
  const sourceOpened = opened.length > 0
  const error = open.error || accept.error || reject.error
  return (
    <div className="space-y-2" data-testid="proposal-review">
      <p className="text-muted-foreground">
        Proposed by the case agent{model ? ` (${model})` : ""}
        {forName ? ` for ${forName}` : ""}. Nothing in the case has changed. A person accepts it only after opening a
        cited source.
      </p>
      {why && <p className="text-sm">{why}</p>}
      <div>
        <span className="block font-mono text-[11px] uppercase tracking-[0.12em] text-muted-foreground">Cited sources</span>
        <ul className="space-y-1">
          {citations.map((citation) => {
            const href = citationHref(caseId, citation)
            const seen = opened.includes(citation)
            return (
              <li key={citation} className="flex flex-wrap items-center gap-2">
                <span>{citationLabels[citation] || citation}</span>
                {href ? (
                  <a
                    href={href}
                    target="_blank"
                    rel="noopener"
                    className="font-medium underline underline-offset-2"
                    data-testid="proposal-open-source"
                    onClick={() => open.mutate(citation)}
                  >
                    Open source
                  </a>
                ) : (
                  <span className="text-muted-foreground">(no link)</span>
                )}
                {seen && <span className="text-[#15653f] dark:text-[#a7e3bf]">✓ opened</span>}
              </li>
            )
          })}
        </ul>
      </div>
      {canEdit && (
        <>
          {acceptExtra}
          <div className="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              className="bg-[#15653f] text-white hover:bg-[#0f5133]"
              disabled={!sourceOpened || !!acceptBlocked || accept.isPending}
              title={!sourceOpened ? "Open a cited source first" : acceptBlocked || undefined}
              data-testid="proposal-accept"
              onClick={() => accept.mutate()}
            >
              <span aria-hidden="true">✓</span>
              {acceptLabel}
            </Button>
            <Button size="sm" variant="outline" aria-expanded={rejecting} onClick={() => setRejecting(true)}>
              Reject
            </Button>
            {!sourceOpened && <span className="text-muted-foreground">Open a cited source to accept.</span>}
            {sourceOpened && acceptBlocked && <span className="text-muted-foreground">{acceptBlocked}</span>}
          </div>
          {rejecting && (
            <form
              className="space-y-2"
              onSubmit={(event) => {
                event.preventDefault()
                if (reason.trim()) reject.mutate()
              }}
            >
              <textarea
                aria-label="Why the proposal is wrong"
                required
                className="w-full rounded border p-2 text-sm"
                rows={2}
                value={reason}
                onChange={(event) => setReason(event.target.value)}
              />
              <div className="flex gap-2">
                <Button size="sm" type="submit" disabled={!reason.trim() || reject.isPending}>
                  Record the rejection
                </Button>
                <Button size="sm" variant="outline" type="button" onClick={() => setRejecting(false)}>
                  Cancel
                </Button>
              </div>
            </form>
          )}
        </>
      )}
      {error && <p role="alert">{error.message}</p>}
    </div>
  )
}
