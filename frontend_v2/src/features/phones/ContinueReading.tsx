import { useQuery } from "@tanstack/react-query"
import { BookOpenCheck } from "lucide-react"
import type { ReactNode } from "react"
import { Link } from "react-router-dom"
import { readingSpots } from "./lib/continue-reading"
import { instantWords } from "./lib/time-words"
import { getContinueWork, shareFailure, type ContinueThread, type ContinueWork } from "./review-share"
import { fmt } from "./ui/count-sentence"

/**
 * Continue reading (07 J-15 step 1), on the Phone summary and in the case's Your work feed: assigned reviews from the
 * server, each open thread with its last position, and the threads opened on this browser (kept as ids; their titles
 * come from the server).
 */
function threadLink(caseId: string, extraction: string, thread: string, at?: string | null) {
  const p = new URLSearchParams({ thread })
  if (at) p.set("at", at)
  return `/cases/${encodeURIComponent(caseId)}/phones/${encodeURIComponent(extraction)}/records/conversations?${p.toString()}`
}

function useContinueWork(caseId: string) {
  const spots = readingSpots(caseId).map((s) => ({ thread: s.thread, record: s.record }))
  return useQuery({
    queryKey: ["phone-continue-reading", caseId, spots],
    queryFn: () => getContinueWork(caseId, spots),
    enabled: !!caseId,
    retry: false,
    staleTime: 60_000,
  })
}

function only(work: ContinueWork, extraction?: string): ContinueWork {
  if (!extraction) return work
  const mine = (t: ContinueThread) => t.extraction_id === extraction
  return {
    assigned: work.assigned.filter((a) => a.phones.includes(extraction)).map((a) => ({ ...a, items: a.items.filter(mine), next: a.next.filter(mine) })),
    reading: work.reading.filter((r) => r.extraction_id === extraction),
  }
}

function WorkList({ caseId, work }: { caseId: string; work: ContinueWork }) {
  return (
    <ul className="flex flex-col gap-1.5">
      {work.assigned.map((a) => (
        <li key={a.task_id} data-testid="continue-assigned">
          <p>{a.title}: {fmt(a.open)} of {fmt(a.total)} still open.</p>
          {a.kind === "readings" ? (
            <Link className="underline underline-offset-2" to={`/cases/${encodeURIComponent(caseId)}/phone-review`}>Open the readings to re-check</Link>
          ) : (
            <ul className="flex flex-col gap-0.5">
              {a.items.map((t) => (
                <li key={t.thread_key}>
                  <Link className="underline underline-offset-2" to={threadLink(caseId, t.extraction_id, t.thread_key, t.position?.event_uid)}>{t.title ?? "Open this thread"}</Link>
                  {t.position ? ` ${t.position.by_name} stopped ${t.position.instant ? `at ${instantWords(t.position.instant, "UTC")}` : "at a saved message"}.` : ""}
                </li>
              ))}
              {a.next.map((t) => (
                <li key={t.thread_key}>
                  Next: <Link className="underline underline-offset-2" to={threadLink(caseId, t.extraction_id, t.thread_key)}>{t.title ?? "Open this thread"}</Link>
                </li>
              ))}
            </ul>
          )}
        </li>
      ))}
      {work.reading.map((r) => (
        <li key={r.thread_key} data-testid="continue-casual">
          <Link className="underline underline-offset-2" to={threadLink(caseId, r.extraction_id, r.thread_key, r.record)}>{r.title}</Link>
          {" "}<span className="text-muted-foreground">{r.phone}, opened on this browser</span>
        </li>
      ))}
    </ul>
  )
}

/** The Phone summary's section. */
export function ContinueReading({ caseId, extraction, empty }: { caseId: string; extraction: string; empty: ReactNode }) {
  const q = useContinueWork(caseId)
  if (q.isLoading) return <p role="status">Finding where you stopped.</p>
  if (q.isError) return <p role="alert">{shareFailure(q.error, "Continue reading could not be loaded.")}</p>
  const work = only(q.data!, extraction)
  return work.assigned.length || work.reading.length ? <WorkList caseId={caseId} work={work} /> : <>{empty}</>
}

/** The block in the case's Your work feed. A case with nothing to continue shows nothing. */
export function ContinueReadingFeed({ caseId }: { caseId: string }) {
  const q = useContinueWork(caseId)
  if (q.isError) return <p role="alert" className="border-t border-border px-4 py-3 text-xs">{shareFailure(q.error, "Continue reading could not be loaded.")}</p>
  const work = q.data
  if (!work || (!work.assigned.length && !work.reading.length)) return null
  return (
    <section aria-label="Continue reading" className="border-t border-border px-4 py-3 text-xs">
      <div className="mb-1.5 flex items-center gap-2">
        <BookOpenCheck className="size-3.5 text-sky-600" />
        <h3 className="font-semibold">Continue reading</h3>
      </div>
      <WorkList caseId={caseId} work={work} />
    </section>
  )
}
