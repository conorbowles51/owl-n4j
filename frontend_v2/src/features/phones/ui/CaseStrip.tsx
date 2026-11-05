import { useQuery, useQueryClient } from "@tanstack/react-query"
import { BookOpen, Keyboard } from "lucide-react"
import { lazy, Suspense, useEffect, useMemo, useRef, useState, type MouseEvent } from "react"
import { useLocation, useNavigate } from "react-router-dom"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { JobTray } from "@/components/ui/job-tray"
import { useTick } from "@/components/ui/progress-time"
import { JOB_STARTED_EVENT } from "@/lib/job-started"
import { installKeymap } from "@/lib/keymap"
import { getJobs, JOB_FRESH_MS, JOB_POLL_MS, jobsQueryKey, justFinished, trayJob } from "@/features/phones/job-list"
import { phonesQuery } from "@/features/phones/phones-query"
import { PHONE_GUIDES } from "@/features/phones/guide"
import { KeymapOverlay } from "./KeymapOverlay"
import { guideAnchor } from "./screen-guide"
import { useBindings } from "./use-bindings"

// The guide (markdown and its renderer) loads when Guide is pressed, not with every case page.
const GuideDialog = lazy(() => import("@/components/ui/guide-dialog").then((m) => ({ default: m.GuideDialog })))

const n = (v: number) => v.toLocaleString("en-US")

function HeaderJobs({ caseId, onList }: { caseId: string; onList: (jobs: number) => void }) {
  const client = useQueryClient()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const q = useQuery({
    queryKey: jobsQueryKey(caseId),
    queryFn: () => getJobs(caseId),
    staleTime: JOB_FRESH_MS,
    refetchOnWindowFocus: true,
    // one request per tab while something runs, none when idle and none from a hidden tab
    refetchInterval: (query) => (query.state.data?.active ? JOB_POLL_MS : false),
  })
  const list = q.data
  const now = useTick(!!list?.active, Date.now)

  // told at once when this tab starts a job; a new screen looks again if the last read is old
  useEffect(() => {
    const look = () => void client.invalidateQueries({ queryKey: jobsQueryKey(caseId) })
    window.addEventListener(JOB_STARTED_EVENT, look)
    return () => window.removeEventListener(JOB_STARTED_EVENT, look)
  }, [client, caseId])
  useEffect(() => {
    void client.refetchQueries({ queryKey: jobsQueryKey(caseId), stale: true })
  }, [client, caseId, pathname])

  // the notice and link when a job this tab watched has finished (07 4.7)
  const watching = useRef(new Set<string>())
  useEffect(() => {
    if (!list) return
    for (const j of justFinished(watching.current, list.items)) {
      const action = j.href ? { label: "Open", onClick: () => (j.href!.startsWith("/cases/") ? navigate(j.href!) : window.location.assign(j.href!)) } : undefined
      if (j.state === "failed") toast.error(`${j.title} stopped.`, { description: j.error ?? undefined, action })
      else if (j.state === "cancelled") toast(`${j.title}: cancelled.`, { description: j.note ?? undefined, action })
      else toast.success(`${j.title}: done.`, { description: j.note ?? undefined, action })
    }
    watching.current = new Set(list.items.filter((j) => j.state === "running").map((j) => j.id))
  }, [list, navigate])

  const jobs = useMemo(() => (list?.items ?? []).map((j) => trayJob(j, Date.parse(list!.read_at))), [list])
  useEffect(() => onList(jobs.length), [jobs.length, onList])

  // a line's link stays inside the app; a file link is left to the browser
  const stayInApp = (e: MouseEvent) => {
    const href = (e.target as HTMLElement).closest("a")?.getAttribute("href")
    if (href?.startsWith("/cases/")) {
      e.preventDefault()
      navigate(href)
    }
  }
  const footer = (
    <div className="mt-2 flex flex-col gap-1 text-sm">
      {q.isError && <p role="alert">The job list could not be read. Long work carries on; it shows here again when the list can be read.</p>}
      {list && list.unavailable.length > 0 && <p role="alert">Not shown, could not be read: {list.unavailable.join(", ")}.</p>}
      {list && list.older_finished > 0 && <p>{n(list.older_finished)} older finished {list.older_finished === 1 ? "job is" : "jobs are"} not listed.</p>}
    </div>
  )
  return (
    <div onClickCapture={stayInApp}>
      <JobTray jobs={jobs} now={now} footer={footer} />
    </div>
  )
}

function GuideButton() {
  const { pathname } = useLocation()
  const [open, setOpen] = useState<{ anchor?: string } | null>(null)
  return (
    <>
      <Button variant="outline" size="sm" onClick={() => setOpen({ anchor: guideAnchor(pathname) })}>
        <BookOpen className="size-4" aria-hidden="true" />
        Guide
      </Button>
      {open && (
        <Suspense fallback={<span role="status" className="text-sm">Opening the guide</span>}>
          <GuideDialog guides={PHONE_GUIDES} noTrigger defaultOpen initial="user" anchor={open.anchor} onOpenChange={(v) => { if (!v) setOpen(null) }} />
        </Suspense>
      )}
    </>
  )
}

/**
 * The thin strip above a phone case's screens: the job tray, the Guide at this screen's part, and the keys. It sits
 * outside the scrolling content so it stays in view (07 4.7, 4.9, 9), and shows only for a case with a phone or a
 * phone job: other cases keep their whole screen.
 */
export default function CaseStrip({ caseId }: { caseId: string }) {
  const phones = useQuery({ ...phonesQuery(caseId), staleTime: 60_000 })
  const [jobs, setJobs] = useState(0)
  const [keys, setKeys] = useState(false)
  const bindings = useBindings()
  useEffect(() => installKeymap(), [])
  const hasPhones = (phones.data?.phones.length ?? 0) > 0
  const shown = hasPhones || jobs > 0
  return (
    <>
      {/* always mounted, so a new first phone's job is seen; hidden until there is something to say */}
      <div
        role="region"
        aria-label="Phone help and jobs"
        className={shown ? "flex shrink-0 items-center justify-end gap-2 border-b border-border bg-card px-3 py-1" : "hidden"}
      >
        {hasPhones && bindings.length > 0 && (
          <Button variant="ghost" size="sm" onClick={() => setKeys(true)}>
            <Keyboard className="size-4" aria-hidden="true" />
            Keys (?)
          </Button>
        )}
        {hasPhones && <GuideButton />}
        <HeaderJobs caseId={caseId} onList={setJobs} />
      </div>
      {hasPhones && <KeymapOverlay open={keys} onOpenChange={setKeys} />}
    </>
  )
}
