import { useState } from "react"
import { Link } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { ReviewStatusLine } from "./ReviewQueuePanel"
import { useReviewCases, useReviewQueue, useReviewStatus } from "../lib/review-queue"

/** This case's status line, with the way into its review queue, and the same line for the other cases. */
export function CaseReviewStatus({
  caseId,
  active,
  onOpen,
}: {
  caseId: string
  active: boolean
  onOpen: () => void
}) {
  const queue = useReviewQueue(caseId, [], active)
  const [showCases, setShowCases] = useState(false)
  if (!queue.data && !queue.isError)
    return (
      <p role="status" className="text-sm text-muted-foreground">
        Counting imported statements and work waiting for you…
      </p>
    )
  return (
    <section aria-label="Where this case stands" className="rounded border p-3 space-y-2">
      {queue.isError ? (
        <p role="alert" className="text-sm">
          The statement status could not be loaded.{" "}
          <Button variant="link" onClick={() => void queue.refetch()}>
            Try again
          </Button>
        </p>
      ) : (
        <div className="flex flex-wrap items-center gap-3">
          <ReviewStatusLine data={queue.data!} />
          <Button size="sm" variant={queue.data!.counts.waiting ? "primary" : "outline"} onClick={onOpen}>
            {queue.data!.counts.waiting
              ? `Review ${queue.data!.counts.waiting} waiting for you`
              : "Open review queue"}
          </Button>
        </div>
      )}
      <details onToggle={(event) => setShowCases((event.target as HTMLDetailsElement).open)}>
        <summary className="cursor-pointer text-sm">All financial cases</summary>
        {showCases && <OtherCases currentCaseId={caseId} />}
      </details>
    </section>
  )
}

function OtherCases({ currentCaseId }: { currentCaseId: string }) {
  const cases = useReviewCases()
  if (cases.isError)
    return (
      <p role="alert" className="text-sm">
        The case list could not be loaded.
      </p>
    )
  if (!cases.data) return <p role="status" className="text-sm">Loading cases…</p>
  if (!cases.data.length) return <p className="text-sm">No case has statements in Financial yet.</p>
  return (
    <ul className="mt-2 divide-y text-sm" aria-label="Financial cases">
      {cases.data.map((entry) => (
        <li key={entry.case_id} className="py-2 space-y-1">
          <Link
            className="font-medium underline underline-offset-2"
            to={`/cases/${entry.case_id}/financial?view=statements&queue=1`}
          >
            {entry.title}
            {entry.case_id === currentCaseId ? " (this case)" : ""}
          </Link>
          <CaseLine caseId={entry.case_id} />
        </li>
      ))}
    </ul>
  )
}

function CaseLine({ caseId }: { caseId: string }) {
  const status = useReviewStatus(caseId)
  if (status.isError) return <p className="text-xs">Status could not be loaded.</p>
  if (!status.data) return <p className="text-xs text-muted-foreground">Counting…</p>
  return <ReviewStatusLine data={status.data} />
}
