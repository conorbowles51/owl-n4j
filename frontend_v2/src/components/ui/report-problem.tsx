import { useId, useState } from "react"
import { MessageSquareWarning } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog"
import { fetchAPI, lastRequestId } from "@/lib/api-client"

/**
 * Report a problem (07 section 9): a button on every phone screen. The report holds the screen, the scope as kinds
 * and counts, the action chosen from a list, whether a refresh changes it, the build, the last request id, the
 * window size and the component ids of the area, plus an optional "What did you expect?". No screenshot is taken.
 * The text stays in the case's records; the team is told only ids, kinds, counts and the build.
 */

export const ACTIONS: { id: string; words: string }[] = [
  { id: "reading", words: "Reading records" },
  { id: "searching", words: "Searching" },
  { id: "filtering", words: "Filtering or choosing dates" },
  { id: "selecting", words: "Selecting rows" },
  { id: "adding-to", words: "Adding to a dossier, finding or note" },
  { id: "deciding", words: "Confirming or correcting" },
  { id: "copying", words: "Copying" },
  { id: "exporting", words: "Exporting" },
  { id: "opening-a-record", words: "Opening a record" },
  { id: "waiting", words: "Waiting for something to load" },
  { id: "other", words: "Something else" },
]
const REFRESH = [
  { id: "no", words: "No, it stays the same" },
  { id: "yes", words: "Yes, refreshing changes it" },
  { id: "not-tried", words: "I have not tried" },
]
export const EXPECTED_MAX = 2000

export interface ProblemReport {
  screen: string
  action_kind: string
  refresh_changes: string
  build_id: string
  last_request_id: string | null
  scope: Record<string, number>
  components: string[]
  viewport_w: number
  viewport_h: number
  expected: string | null
}

export function buildId(): string {
  const meta = typeof document !== "undefined" ? document.querySelector('meta[name="loupe-build"]')?.getAttribute("content") : null
  return meta && /^([0-9a-f]{7,64}|dev)$/.test(meta) ? meta : "dev"
}

export type ReportSender = (caseId: string, report: ProblemReport) => Promise<{ id: string; reference: string }>
export const sendReport: ReportSender = (caseId, report) =>
  fetchAPI(`/api/cases/${caseId}/ui-problem-reports`, { method: "POST", body: report })

export function ReportProblem({
  caseId,
  screen,
  scope = {},
  components = [],
  send = sendReport,
  defaultOpen = false,
}: {
  caseId: string
  screen: string
  /** Kinds and counts in view, e.g. { messages: 2140, phones: 3 }. Never names or values. */
  scope?: Record<string, number>
  components?: string[]
  send?: ReportSender
  defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  const [action, setAction] = useState("")
  const [refresh, setRefresh] = useState("not-tried")
  const [expected, setExpected] = useState("")
  const [state, setState] = useState<{ kind: "idle" | "sending" | "saved" | "failed"; words?: string }>({ kind: "idle" })
  const ids = { action: useId(), expected: useId(), refresh: useId() }

  const submit = async () => {
    if (!action) return
    setState({ kind: "sending" })
    try {
      const reply = await send(caseId, {
        screen,
        action_kind: action,
        refresh_changes: refresh,
        build_id: buildId(),
        last_request_id: lastRequestId(),
        scope,
        components,
        viewport_w: Math.round(window.innerWidth),
        viewport_h: Math.round(window.innerHeight),
        expected: expected.trim() || null,
      })
      setState({ kind: "saved", words: `Report saved. Reference ${reply.reference}. Thank you.` })
    } catch (e) {
      setState({ kind: "failed", words: `The report was not saved${e instanceof Error && e.message ? `: ${e.message}` : ""}. Your answers are kept; send again.` })
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(value) => {
        setOpen(value)
        if (!value && state.kind === "saved") {
          setAction("")
          setRefresh("not-tried")
          setExpected("")
          setState({ kind: "idle" })
        }
      }}
    >
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <MessageSquareWarning className="size-4" aria-hidden="true" />
          Report a problem
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Report a problem</DialogTitle>
          <DialogDescription>
            Loupe records this screen, how many items were in view, the build and the window size. No screenshot is
            taken. What you type is kept in this case's records only.
          </DialogDescription>
        </DialogHeader>
        {state.kind === "saved" ? (
          <p role="status" className="text-sm">{state.words}</p>
        ) : (
          <form
            className="flex flex-col gap-4"
            onSubmit={(event) => {
              event.preventDefault()
              void submit()
            }}
          >
            <div className="flex flex-col gap-1">
              <label htmlFor={ids.action} className="text-sm font-medium">What were you doing?</label>
              <select
                id={ids.action}
                required
                value={action}
                onChange={(e) => setAction(e.target.value)}
                className="h-9 rounded-md border border-input bg-background px-2 text-sm"
              >
                <option value="">Choose one</option>
                {ACTIONS.map((a) => (
                  <option key={a.id} value={a.id}>{a.words}</option>
                ))}
              </select>
            </div>
            <fieldset className="flex flex-col gap-1">
              <legend className="mb-1 text-sm font-medium">Does refreshing the page change it?</legend>
              {REFRESH.map((r) => (
                <label key={r.id} className="flex items-center gap-2 text-sm">
                  <input type="radio" name={ids.refresh} value={r.id} checked={refresh === r.id} onChange={() => setRefresh(r.id)} />
                  {r.words}
                </label>
              ))}
            </fieldset>
            <div className="flex flex-col gap-1">
              <label htmlFor={ids.expected} className="text-sm font-medium">What did you expect? (optional)</label>
              <textarea
                id={ids.expected}
                value={expected}
                maxLength={EXPECTED_MAX}
                rows={4}
                onChange={(e) => setExpected(e.target.value)}
                className="rounded-md border border-input bg-background p-2 text-sm"
              />
              <span className="text-xs text-muted-foreground">{expected.length.toLocaleString("en-US")} of {EXPECTED_MAX.toLocaleString("en-US")} characters</span>
            </div>
            {state.kind === "failed" && <p role="alert" className="text-sm text-status-error">{state.words}</p>}
            <div className="flex justify-end gap-2">
              <Button type="submit" disabled={!action || state.kind === "sending"}>
                {state.kind === "sending" ? "Sending…" : "Send report"}
              </Button>
            </div>
          </form>
        )}
      </DialogContent>
    </Dialog>
  )
}
