import { useState } from "react"
import { History, RefreshCw } from "lucide-react"
import { useQuery } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { fetchAPI } from "@/lib/api-client"
import { useCases } from "@/features/cases/hooks/use-cases"

interface ActivityFile {
  id: string | null
  filename: string | null
  sha256: string | null
  size: number | null
}

interface ActivityEvent {
  id: number
  at: string
  action: string
  action_label: string
  user_name: string | null
  user_email: string | null
  case_id: string | null
  source_address: string | null
  user_agent: string | null
  session_ref: string | null
  origin: string | null
  origin_label: string | null
  request_path: string | null
  details: {
    files?: ActivityFile[]
    file_count?: number
    reason?: string
    how?: string
    batch_id?: string | null
    continued?: boolean
  } & Record<string, unknown>
}

interface ActivityResponse {
  events: ActivityEvent[]
  total: number
  actions: Record<string, string>
}

const PAGE = 100
const ALL = "all"

/** Who did what, from where: sign-ins, uploads and Financial entries. Admins only (server enforced). */
export function ActivityPage() {
  const [caseId, setCaseId] = useState(ALL)
  const [action, setAction] = useState(ALL)
  const [user, setUser] = useState("")
  const [since, setSince] = useState("")
  const [until, setUntil] = useState("")
  const [offset, setOffset] = useState(0)
  const cases = useCases("all_cases", true)

  const query = useQuery({
    queryKey: ["admin", "activity", caseId, action, user, since, until, offset],
    queryFn: () => {
      const qs = new URLSearchParams({ limit: String(PAGE), offset: String(offset) })
      if (caseId !== ALL) qs.set("case_id", caseId)
      if (action !== ALL) qs.set("action", action)
      if (user.trim()) qs.set("user", user.trim())
      if (since) qs.set("since", new Date(`${since}T00:00:00`).toISOString())
      if (until) qs.set("until", new Date(`${until}T23:59:59.999`).toISOString())
      return fetchAPI<ActivityResponse>(`/api/activity?${qs}`)
    },
  })
  const caseTitle = (id: string | null) =>
    (id && cases.data?.find((item) => item.id === id)?.title) || id || ""
  const actions = query.data?.actions ?? {}
  const total = query.data?.total ?? 0
  const reset = () => setOffset(0)

  return (
    <div className="flex h-full flex-col bg-background">
      <div className="flex flex-wrap items-center gap-2 border-b border-border bg-card px-4 py-2">
        <History className="size-4 text-amber-500" />
        <span className="font-display text-sm font-semibold">Activity</span>
        <div className="flex-1" />
        <Select value={caseId} onValueChange={(value) => { setCaseId(value); reset() }}>
          <SelectTrigger className="w-56" aria-label="Case">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All cases</SelectItem>
            {(cases.data ?? []).map((item) => (
              <SelectItem key={item.id} value={item.id}>
                {item.title}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={action} onValueChange={(value) => { setAction(value); reset() }}>
          <SelectTrigger className="w-56" aria-label="Action">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All actions</SelectItem>
            {Object.entries(actions).map(([key, label]) => (
              <SelectItem key={key} value={key}>
                {label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Input
          aria-label="Person (email or name)"
          placeholder="Person (email or name)"
          value={user}
          onChange={(event) => { setUser(event.target.value); reset() }}
          className="w-56"
        />
        <Input aria-label="From date" type="date" value={since}
          onChange={(event) => { setSince(event.target.value); reset() }} className="w-40" />
        <Input aria-label="To date" type="date" value={until}
          onChange={(event) => { setUntil(event.target.value); reset() }} className="w-40" />
        <Button variant="ghost" size="sm" aria-label="Refresh" onClick={() => void query.refetch()}>
          <RefreshCw className="size-3.5" />
        </Button>
      </div>
      <p className="border-b border-border px-4 py-2 text-xs text-muted-foreground">
        Recorded since this trail was switched on (27 Oct 2026): sign-ins, sign-outs, evidence uploads and every addition to
        Financial, with the address the browser connected from. Earlier events show only what the
        database recorded at the time (who and when, never the address). The record cannot be edited
        or deleted.
      </p>
      <ScrollArea className="flex-1">
        <table className="w-full text-left text-xs">
          <thead className="sticky top-0 bg-card text-muted-foreground">
            <tr>
              <th className="px-3 py-2">When</th>
              <th className="px-3 py-2">Who</th>
              <th className="px-3 py-2">What</th>
              <th className="px-3 py-2">Case</th>
              <th className="px-3 py-2">From</th>
              <th className="px-3 py-2">Details</th>
            </tr>
          </thead>
          <tbody>
            {(query.data?.events ?? []).map((event) => (
              <tr key={event.id} className="border-t border-border align-top">
                <td className="whitespace-nowrap px-3 py-2">
                  {new Date(event.at).toLocaleString(undefined, { timeZoneName: "short" })}
                </td>
                <td className="px-3 py-2">
                  {event.user_name || event.user_email || "Unknown"}
                  {event.user_name && event.user_email && (
                    <span className="block text-muted-foreground">{event.user_email}</span>
                  )}
                </td>
                <td className="px-3 py-2">
                  {event.action_label}
                  {event.details.reason && (
                    <span className="block text-muted-foreground">Reason: {event.details.reason}</span>
                  )}
                </td>
                <td className="px-3 py-2">{caseTitle(event.case_id)}</td>
                <td className="px-3 py-2">
                  <span className="font-mono">{event.source_address || "not recorded"}</span>
                  {event.origin_label && <span className="block">{event.origin_label}</span>}
                  {event.user_agent && (
                    <span className="block max-w-xs truncate text-muted-foreground" title={event.user_agent}>
                      {event.user_agent}
                    </span>
                  )}
                  {event.session_ref && (
                    <span className="block font-mono text-muted-foreground" title="Sign-in fingerprint: the same value means the same sign-in">
                      sign-in {event.session_ref}
                    </span>
                  )}
                </td>
                <td className="px-3 py-2">
                  {event.details.files?.length ? (
                    <details>
                      <summary>
                        {event.details.files.length} {event.details.files.length === 1 ? "file" : "files"}
                        {event.details.batch_id ? ` · batch ${event.details.batch_id.slice(0, 8)}` : ""}
                      </summary>
                      <ul className="mt-1 space-y-0.5">
                        {event.details.files.map((file, index) => (
                          <li key={file.id ?? index} className="break-all">
                            {file.filename}
                            {file.sha256 && (
                              <span className="block font-mono text-muted-foreground">sha256 {file.sha256}</span>
                            )}
                          </li>
                        ))}
                      </ul>
                    </details>
                  ) : event.details.batch_id ? (
                    `batch ${event.details.batch_id.slice(0, 8)}`
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!query.data?.events.length && (
          <p className="py-8 text-center text-muted-foreground">
            {query.isLoading ? "Loading activity…" : query.isError ? "Activity could not be loaded." : "No activity matches these filters."}
          </p>
        )}
      </ScrollArea>
      <div className="flex items-center gap-2 border-t border-border px-4 py-2 text-xs">
        <span>
          {total ? `${offset + 1}–${Math.min(offset + PAGE, total)} of ${total}` : "0 events"}
        </span>
        <div className="flex-1" />
        <Button variant="outline" size="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
          Newer
        </Button>
        <Button variant="outline" size="sm" disabled={offset + PAGE >= total} onClick={() => setOffset(offset + PAGE)}>
          Older
        </Button>
      </div>
    </div>
  )
}
