import { useState } from "react"
import { Link } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { ApiError } from "@/lib/api-client"
import {
  FLAG_PAGE,
  FLAG_STATE_WORDS,
  ORIGIN_WORDS,
  PROPOSAL_PAGE,
  PROPOSAL_STATE_WORDS,
  flagActions,
  flagKindWords,
  flagSubjectWords,
  rangeWords,
  readingWords,
  registryApi,
  retryUnlessRefused,
  saveFile,
  type FlagAction,
  type FlagState,
  type MappingProposal,
  type ProposalOrigin,
  type ProposalState,
  type RegistryFlag,
} from "../phone-registry"

const FLAG_ORDER: FlagState[] = ["open", "mapping_needed", "acknowledged", "mapped", "dismissed"]
const PROPOSAL_ORDER: ProposalState[] = ["draft", "exported", "rejected"]

function when(iso: string | null | undefined) {
  if (!iso) return ""
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString()
}

function errorWords(err: unknown): string {
  if (err instanceof ApiError && err.status === 403) return "Only an administrator can see the phone registry."
  if (err instanceof ApiError) return err.message
  return err instanceof Error ? err.message : "Something went wrong."
}

function Pager(props: { offset: number; shown: number; total: number; size: number; onChange: (o: number) => void }) {
  const { offset, shown, total, size, onChange } = props
  return (
    <div className="flex items-center gap-2 text-xs text-muted-foreground" data-testid="pager">
      <span>{rangeWords(offset, shown, total)}</span>
      <Button size="sm" variant="outline" disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - size))}>
        Previous
      </Button>
      <Button size="sm" variant="outline" disabled={offset + shown >= total} onClick={() => onChange(offset + size)}>
        Next
      </Button>
    </div>
  )
}

/** A reason box: the action is refused until a reason is typed (02 3.4: dismiss "with reason"; the server asks one
 * for every transition). */
function ReasonForm(props: { label: string; busy: boolean; error?: string | null; onCancel: () => void; onSubmit: (r: string) => void }) {
  const [reason, setReason] = useState("")
  return (
    <div className="mt-2 flex flex-col gap-2 rounded border border-border p-2">
      <label className="text-xs">
        Reason (required)
        <Textarea aria-label="Reason" value={reason} onChange={(e) => setReason(e.target.value)} rows={2} />
      </label>
      {props.error && <p className="text-xs text-destructive">{props.error}</p>}
      <div className="flex gap-2">
        <Button size="sm" disabled={!reason.trim() || props.busy} onClick={() => props.onSubmit(reason.trim())}>
          {props.label}
        </Button>
        <Button size="sm" variant="ghost" onClick={props.onCancel}>
          Cancel
        </Button>
      </div>
    </div>
  )
}

function FlagRow({ flag }: { flag: RegistryFlag }) {
  const qc = useQueryClient()
  const [action, setAction] = useState<FlagAction | null>(null)
  const m = useMutation({
    mutationFn: (v: { to: FlagAction["to"]; reason: string }) => registryApi.transition(flag.id, v.to, v.reason),
    onSuccess: () => {
      setAction(null)
      void qc.invalidateQueries({ queryKey: ["admin", "phone-registry", "flags"] })
    },
  })
  const rb = flag.raised_by
  return (
    <tr className="border-b border-border align-top" data-testid={`flag-${flag.id}`}>
      <td className="py-2 pr-3">
        <div className="font-medium">{flagKindWords(flag.flag_kind)}</div>
        <div className="text-xs text-muted-foreground">{flagSubjectWords(flag)}</div>
        {flag.severity === "blocks_mapping" && <div className="text-xs text-destructive">Holds back a mapping</div>}
      </td>
      <td className="py-2 pr-3 text-xs">{FLAG_STATE_WORDS[flag.state] ?? flag.state}</td>
      <td className="py-2 pr-3 text-xs">
        <div>{when(flag.raised_at)}</div>
        {rb?.link ? (
          <Link className="underline" to={rb.link}>
            {rb.label ?? "Phone"}
            {rb.case_title ? ` in ${rb.case_title}` : ""}
          </Link>
        ) : rb ? (
          <span>A phone no longer in any case</span>
        ) : (
          <span>From the registry seed</span>
        )}
      </td>
      <td className="py-2 pr-3 text-xs">
        {flag.last_event ? (
          <>
            <div>
              {FLAG_STATE_WORDS[flag.last_event.to as FlagState] ?? flag.last_event.to} by {flag.last_event.by ?? "the system"},{" "}
              {when(flag.last_event.at)}
            </div>
            <div className="text-muted-foreground">{flag.last_event.reason}</div>
          </>
        ) : (
          "No change yet"
        )}
      </td>
      <td className="py-2 text-xs">
        <div className="flex flex-wrap gap-1">
          {flagActions(flag.state).map((a) => (
            <Button key={a.to} size="sm" variant={action?.to === a.to ? "primary" : "outline"} onClick={() => setAction(a)}>
              {a.label}
            </Button>
          ))}
        </div>
        {action && (
          <ReasonForm
            key={action.to}
            label={action.label}
            busy={m.isPending}
            error={m.error ? errorWords(m.error) : null}
            onCancel={() => setAction(null)}
            onSubmit={(reason) => m.mutate({ to: action.to, reason })}
          />
        )}
      </td>
    </tr>
  )
}

function FlagsTab() {
  const [state, setState] = useState<FlagState | undefined>("open")
  const [offset, setOffset] = useState(0)
  const q = useQuery({
    queryKey: ["admin", "phone-registry", "flags", state, offset],
    queryFn: () => registryApi.flags(state, offset),
    placeholderData: (prev) => prev,
    retry: retryUnlessRefused,
  })
  const pick = (s: FlagState | undefined) => {
    setState(s)
    setOffset(0)
  }
  if (q.error) return <p className="text-sm text-destructive">{errorWords(q.error)}</p>
  const data = q.data
  const all = data ? Object.values(data.counts).reduce((a, b) => a + b, 0) : 0
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-1" role="group" aria-label="Flag state">
        {FLAG_ORDER.map((s) => (
          <Button key={s} size="sm" variant={state === s ? "primary" : "outline"} onClick={() => pick(s)}>
            {FLAG_STATE_WORDS[s]} ({data ? data.counts[s].toLocaleString() : "…"})
          </Button>
        ))}
        <Button size="sm" variant={state === undefined ? "primary" : "outline"} onClick={() => pick(undefined)}>
          All ({data ? all.toLocaleString() : "…"})
        </Button>
      </div>
      {!data ? (
        <p className="text-sm text-muted-foreground">Loading the registry flags…</p>
      ) : (
        <>
          <Pager offset={offset} shown={data.flags.length} total={data.total} size={FLAG_PAGE} onChange={setOffset} />
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs text-muted-foreground">
                <th className="py-1 pr-3">What was found</th>
                <th className="py-1 pr-3">State</th>
                <th className="py-1 pr-3">Raised by</th>
                <th className="py-1 pr-3">Last change</th>
                <th className="py-1">Change</th>
              </tr>
            </thead>
            <tbody>
              {data.flags.map((f) => (
                <FlagRow key={f.id} flag={f} />
              ))}
            </tbody>
          </table>
          {data.flags.length === 0 && <p className="text-sm text-muted-foreground">No flags in this state.</p>}
        </>
      )}
    </div>
  )
}

function ProposalRow({ p }: { p: MappingProposal }) {
  const qc = useQueryClient()
  const [rejecting, setRejecting] = useState(false)
  const refresh = () => void qc.invalidateQueries({ queryKey: ["admin", "phone-registry", "proposals"] })
  const reject = useMutation({
    mutationFn: (reason: string) => registryApi.reject(p.id, reason),
    onSuccess: () => {
      setRejecting(false)
      refresh()
    },
  })
  const download = useMutation({
    mutationFn: () => registryApi.exportFile(p.id),
    onSuccess: (content) => {
      saveFile(`${p.name}.json`, content)
      refresh()
    },
  })
  return (
    <tr className="border-b border-border align-top" data-testid={`proposal-${p.id}`}>
      <td className="py-2 pr-3 text-xs">
        <div className="font-medium">{ORIGIN_WORDS[p.origin] ?? p.origin}</div>
        <div>
          {p.kind} mapping {p.name}
        </div>
        {p.case && (
          <Link className="underline" to={`/cases/${p.case.id}/phone-review`}>
            {p.case.title}
          </Link>
        )}
      </td>
      <td className="py-2 pr-3 text-xs">
        {p.origin === "case_correction" ? (
          <>
            <div>Rule {p.rule_id}</div>
            <div>
              Original reading: <span className="text-muted-foreground">{readingWords(p.original)}</span>
            </div>
            <div>
              Correction: <span className="font-medium">{p.correction_label ?? readingWords(p.correction)}</span>
            </div>
          </>
        ) : (
          <div>Drafted by {p.model ?? "a model"}; not reviewed</div>
        )}
      </td>
      <td className="py-2 pr-3 text-xs">
        {p.decided_by ? (
          <>
            <div>
              {p.decided_by.name}, {when(p.decided_by.at)}
            </div>
            <div className="text-muted-foreground">{p.decided_by.reason}</div>
          </>
        ) : (
          "No person yet"
        )}
      </td>
      <td className="py-2 pr-3 text-xs">
        <div>{PROPOSAL_STATE_WORDS[p.state] ?? p.state}</div>
        {p.last_event && (
          <div className="text-muted-foreground">
            {p.last_event.by ?? "the system"}, {when(p.last_event.at)}: {p.last_event.reason}
          </div>
        )}
      </td>
      <td className="py-2 text-xs">
        {p.state !== "rejected" && (
          <div className="flex flex-wrap gap-1">
            <Button size="sm" variant="outline" disabled={download.isPending} onClick={() => download.mutate()}>
              Download file
            </Button>
            <Button size="sm" variant={rejecting ? "primary" : "outline"} onClick={() => setRejecting(true)}>
              Reject
            </Button>
          </div>
        )}
        {p.state !== "rejected" && (
          <div className="mt-1 text-muted-foreground">
            Edit, review and commit it as <code>{p.file_path}</code>
          </div>
        )}
        {download.error && <p className="text-destructive">{errorWords(download.error)}</p>}
        {rejecting && (
          <ReasonForm
            label="Reject"
            busy={reject.isPending}
            error={reject.error ? errorWords(reject.error) : null}
            onCancel={() => setRejecting(false)}
            onSubmit={(r) => reject.mutate(r)}
          />
        )}
      </td>
    </tr>
  )
}

function ProposalsTab() {
  const [state, setState] = useState<ProposalState | undefined>("draft")
  const [origin, setOrigin] = useState<ProposalOrigin | undefined>(undefined)
  const [offset, setOffset] = useState(0)
  const q = useQuery({
    queryKey: ["admin", "phone-registry", "proposals", state, origin, offset],
    queryFn: () => registryApi.proposals(state, origin, offset),
    placeholderData: (prev) => prev,
    retry: retryUnlessRefused,
  })
  if (q.error) return <p className="text-sm text-destructive">{errorWords(q.error)}</p>
  const data = q.data
  const all = data ? Object.values(data.counts).reduce((a, b) => a + b, 0) : 0
  return (
    <div className="flex flex-col gap-3">
      <p className="text-xs text-muted-foreground">
        A correction made in one case changes only that case. Nothing here changes a mapping for every case: a
        downloaded file is applied only after a person reviews it and commits it.
      </p>
      <div className="flex flex-wrap gap-1" role="group" aria-label="Proposal state">
        {PROPOSAL_ORDER.map((s) => (
          <Button key={s} size="sm" variant={state === s ? "primary" : "outline"} onClick={() => { setState(s); setOffset(0) }}>
            {PROPOSAL_STATE_WORDS[s]} ({data ? data.counts[s].toLocaleString() : "…"})
          </Button>
        ))}
        <Button size="sm" variant={state === undefined ? "primary" : "outline"} onClick={() => { setState(undefined); setOffset(0) }}>
          All ({data ? all.toLocaleString() : "…"})
        </Button>
      </div>
      <div className="flex flex-wrap gap-1" role="group" aria-label="Proposal origin">
        {([undefined, "case_correction", "ai_draft"] as (ProposalOrigin | undefined)[]).map((o) => (
          <Button key={o ?? "all"} size="sm" variant={origin === o ? "primary" : "outline"} onClick={() => { setOrigin(o); setOffset(0) }}>
            {o ? ORIGIN_WORDS[o] : "Any origin"}
          </Button>
        ))}
      </div>
      {!data ? (
        <p className="text-sm text-muted-foreground">Loading the proposals…</p>
      ) : (
        <>
          <Pager offset={offset} shown={data.proposals.length} total={data.total} size={PROPOSAL_PAGE} onChange={setOffset} />
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs text-muted-foreground">
                <th className="py-1 pr-3">From</th>
                <th className="py-1 pr-3">Proposed change</th>
                <th className="py-1 pr-3">Decided by</th>
                <th className="py-1 pr-3">State</th>
                <th className="py-1">Action</th>
              </tr>
            </thead>
            <tbody>
              {data.proposals.map((p) => (
                <ProposalRow key={p.id} p={p} />
              ))}
            </tbody>
          </table>
          {data.proposals.length === 0 && <p className="text-sm text-muted-foreground">No proposals here.</p>}
        </>
      )}
    </div>
  )
}

/** Phone registry (02 sections 3.4 and 6.8): what new phone reports contained that Loupe had not seen, and the
 * corrections made in cases that propose a change for every case. Admins only; the registry is global. */
export function PhoneRegistryPage() {
  return (
    <div className="flex flex-col gap-4">
      <div>
        <h2 className="text-lg font-semibold">Phone registry</h2>
        <p className="text-sm text-muted-foreground">
          Everything phone reports have been seen to contain, for every case. A flag marks something new; a proposal
          suggests a change to how every case reads a kind of record.
        </p>
      </div>
      <Tabs defaultValue="flags">
        <TabsList>
          <TabsTrigger value="flags">Flags</TabsTrigger>
          <TabsTrigger value="proposals">Proposals</TabsTrigger>
        </TabsList>
        <TabsContent value="flags">
          <FlagsTab />
        </TabsContent>
        <TabsContent value="proposals">
          <ProposalsTab />
        </TabsContent>
      </Tabs>
    </div>
  )
}
