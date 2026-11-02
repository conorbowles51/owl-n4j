import { useQuery } from "@tanstack/react-query"
import { Link } from "react-router-dom"
import { getThreads } from "../api"

const n = (v: number) => v.toLocaleString("en-US")

/**
 * The phone's review coverage (07 J-13): how many threads are not yet reviewed, reviewed and partly reviewed. A
 * thread whose messages grew after its review (a Replace, a re-reading or a widened scope) is partly reviewed and
 * says by whom, when, how many it had then and how many were added since (J-13b).
 */
export function ReviewCoverage({ caseId, extraction }: { caseId: string; extraction: string }) {
  const q = useQuery({
    queryKey: ["phone-review-coverage", caseId, extraction],
    queryFn: () => getThreads({ case_id: caseId, phones: [extraction] }, "recent"),
    enabled: !!caseId && !!extraction,
  })
  if (q.isLoading) return <p role="status">Counting reviewed threads.</p>
  if (q.isError || !q.data) return <p role="alert">The review coverage could not be loaded.</p>
  const c = q.data.counts as Record<string, number | undefined>
  const partly = q.data.items.filter((t) => t.review && t.review.added_since > 0)
  return (
    <div className="flex flex-col gap-1">
      <p>Not yet reviewed: {n(c.not_reviewed ?? 0)} of {n(c.threads ?? 0)} threads</p>
      <p>
        Reviewed: {n(c.reviewed ?? 0)}. Partly reviewed: {n(c.partly_reviewed ?? 0)}.
      </p>
      {partly.length > 0 && (
        <ul aria-label="Partly reviewed threads" className="list-disc pl-4">
          {partly.map((t) => (
            <li key={t.thread_key}>
              <Link className="underline" to={`/cases/${encodeURIComponent(caseId)}/conversations?thread=${encodeURIComponent(t.thread_key)}`}>{t.title}</Link>: {t.review!.words}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
