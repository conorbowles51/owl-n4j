import { useState } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { ProposalReview } from "@/features/financial/components/ProposalReview"
import {
  AGENT_PROPOSAL_LABELS,
  acceptAgentProposal,
  alertAmount,
  agentProposalKeys,
  agentProposalOpened,
  listAgentProposals,
  rejectAgentProposal,
  type AgentProposal,
  type LeadAlert,
} from "../agent-proposals"
import { GlossaryPanel } from "./GlossaryPanel"

const STATUSES = [
  ["pending_review", "Waiting for a person"],
  ["accepted", "Accepted"],
  ["rejected", "Rejected"],
] as const

function text(value: unknown) {
  return typeof value === "string" ? value : value == null ? "" : String(value)
}

function ProposalBody({ item }: { item: AgentProposal }) {
  const c = item.content
  if (item.output_type === "entry_draft" || item.output_type === "alternative_explanation") {
    return (
      <div className="space-y-1">
        <p className="text-sm font-semibold">
          {item.output_type === "entry_draft" ? `${text(c.entry_type) === "finding" ? "Finding" : "Note"}: ` : ""}
          {text(c.title)}
        </p>
        {item.output_type === "alternative_explanation" && (
          <p className="text-xs text-muted-foreground">
            An explanation of the facts behind the theory “{text(c.theory_title)}”, from a model that was not shown the
            theory. Accepting adds it as a proposed theory.
          </p>
        )}
        <p className="whitespace-pre-wrap text-sm">{text(c.body)}</p>
      </div>
    )
  }
  if (item.output_type === "control_claim" || item.output_type === "payment_purpose") {
    return (
      <div className="space-y-1">
        <p className="text-sm font-semibold">{text(c.title)}</p>
        <p className="text-xs text-muted-foreground">
          {item.output_type === "control_claim"
            ? "Drafted from the phones' own check. Accepting adds it as a finding about means; the statement's printed holder does not change."
            : "The model's reading of the messages around the payment. Accepting adds it as a finding."}
        </p>
        <p className="whitespace-pre-wrap text-sm">{text(c.body)}</p>
      </div>
    )
  }
  if (item.output_type === "statement_claim") {
    return (
      <div className="space-y-1 text-sm" data-testid="claim-proposal">
        <p className="font-semibold">
          {text(c.kind).replace(/_/g, " ")}
          {text(c.subject_name) ? ` · ${text(c.subject_name)}` : ""}
        </p>
        <blockquote className="border-l-2 pl-2">{text(c.quote)}</blockquote>
        {text(c.window_text) && <p>The source's words for the time: {text(c.window_text)}</p>}
        {text(c.place_text) && <p>The source's words for the place: {text(c.place_text)}</p>}
        {text(c.why) && <p>{text(c.why)}</p>}
        <p className="text-xs text-muted-foreground">
          The model's reading of the source. Accepting adds it to Patterns as a drafted statement; a person then sets its
          time and confirms it, and only a confirmed statement is checked.
        </p>
      </div>
    )
  }
  if (item.output_type === "entity_proposal") {
    return (
      <div className="space-y-1 text-sm" data-testid="entity-proposal">
        <p className="font-semibold">
          {text(c.name)} · {text(c.entity_type)}
        </p>
        <p>{text(c.summary)}</p>
        {text(c.why) && <p>{text(c.why)}</p>}
        <p className="text-xs text-muted-foreground">
          The model's reading of the sources. Accepting adds this entity to the graph, showing that a model proposed it and
          who accepted it.
        </p>
      </div>
    )
  }
  if (item.output_type === "glossary_term") {
    return (
      <div className="space-y-1 text-sm" data-testid="term-proposal">
        <p className="font-semibold">“{text(c.term)}”</p>
        <p>Model reading: {text(c.meaning)}</p>
        {text(c.speaker) && <p>Used by: {text(c.speaker)}</p>}
        {text(c.why) && <p>{text(c.why)}</p>}
        <p className="text-xs text-muted-foreground">
          A model reading, not confirmed. Accepting records the meaning below as your reading, under your name, and joins
          every mention to its ledger rows.
        </p>
      </div>
    )
  }
  if (item.output_type === "link_proposal") {
    return (
      <p className="text-sm">
        Link {text(c.target_type).replace(/_/g, " ")} to “{text(c.entry_title)}” as{" "}
        <strong>{text(c.relationship)}</strong>. {text(c.why)}
      </p>
    )
  }
  if (item.output_type === "timeline_addition") {
    const rows = (Array.isArray(c.rows) ? c.rows : []) as { source_id: string; name?: string; date?: string; status?: string }[]
    return (
      <div className="space-y-1 text-sm">
        <p>Add {rows.length} {rows.length === 1 ? "item" : "items"} to the timeline. {text(c.why)}</p>
        <ul className="list-disc pl-5">
          {rows.map((row) => (
            <li key={row.source_id}>
              {row.date || "no date"} · {row.name || row.source_id}
            </li>
          ))}
        </ul>
      </div>
    )
  }
  // Lead card (connection 2): institution, ending masked to 4, the period a request would cover, alerts by class.
  const counts = (c.counts || {}) as Record<string, number>
  const alerts = (Array.isArray(c.alerts) ? c.alerts : []) as LeadAlert[]
  const period = (c.request_period || null) as { start: string; end: string } | null
  return (
    <div className="space-y-1.5 text-sm" data-testid="lead-card">
      <p className="font-semibold">
        {text(c.institution) || "Institution not named"} · {text(c.account_ending) || "no ending printed"}
      </p>
      {period && (
        <p>
          Period a statement request would cover: {period.start} to {period.end}
        </p>
      )}
      <p>
        Alerts by class:{" "}
        {Object.entries(counts)
          .map(([key, n]) => `${key.replace(/_/g, " ")} ${n}`)
          .join(" · ") || "none"}
      </p>
      {text(c.status_sentence) && <p className="text-muted-foreground">{text(c.status_sentence)}</p>}
      <ul className="space-y-0.5">
        {alerts.map((alert) => (
          <li key={alert.cite} className="text-[13px]">
            {alert.at ? alert.at.slice(0, 16).replace("T", " ") : "no time"} · {alert.evidence_class || "alert"}
            {alertAmount(alert) ? ` · ${alert.direction === "credit" ? "in" : alert.direction === "debit" ? "out" : ""} ${alertAmount(alert)}` : ""}
            {alert.phone ? ` · ${alert.phone}` : ""}
          </li>
        ))}
      </ul>
      {Number(c.alerts_total) > alerts.length && (
        <p className="text-muted-foreground">
          Showing {alerts.length} of {text(c.alerts_total)} alerts.
        </p>
      )}
      <p className="text-xs text-muted-foreground">Each alert is listed and cited on its own; the amounts are not added up.</p>
    </div>
  )
}

function ProposalCard({ caseId, item, canEdit }: { caseId: string; item: AgentProposal; canEdit: boolean }) {
  const client = useQueryClient()
  const [due, setDue] = useState("")
  const [schedule, setSchedule] = useState<string | null>(null)
  const [meaning, setMeaning] = useState<string | null>(null)
  const refresh = () => client.invalidateQueries({ queryKey: agentProposalKeys.all(caseId) })
  const cites = item.content.citations || item.citations.map((c) => c.cite || c.source_id || "").filter(Boolean)
  const labels = Object.fromEntries(item.citations.map((c) => [c.cite || c.source_id || "", c.label]))
  const lead = item.output_type === "lead_card"
  const term = item.output_type === "glossary_term"
  const pending = item.review_status === "pending_review"
  const draftSchedule = lead ? text(item.content.schedule) : ""
  const draftMeaning = term ? text(item.content.meaning) : ""
  const acceptBody = () => {
    if (lead) return { due_at: due, ...(schedule !== null && schedule !== draftSchedule ? { schedule } : {}) }
    if (term) return meaning !== null && meaning !== draftMeaning ? { meaning } : {}
    return {}
  }
  return (
    <li className="space-y-2 rounded-lg border p-3" data-testid="agent-proposal" data-kind={item.output_type}>
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="slate">{AGENT_PROPOSAL_LABELS[item.output_type] || item.output_type}</Badge>
        <span className="text-xs text-muted-foreground">
          Proposed by the case agent{item.proposal.model ? ` (${item.proposal.model})` : ""}
          {item.created_at ? ` · ${item.created_at.slice(0, 10)}` : ""}
        </span>
      </div>
      {pending && item.order_reason && (
        <p className="text-xs text-muted-foreground" data-testid="proposal-order-reason">
          Place in this order: {item.order_reason}
        </p>
      )}
      <ProposalBody item={item} />
      {lead && draftSchedule && (
        <label className="block space-y-1 text-sm">
          <span className="font-medium">Draft production-order schedule</span>
          <span className="block text-xs text-muted-foreground" data-testid="schedule-label">
            {text(item.content.schedule_label)}
          </span>
          <Textarea
            className="min-h-40 font-mono text-xs"
            value={schedule ?? draftSchedule}
            readOnly={!pending || !canEdit}
            onChange={(event) => setSchedule(event.target.value)}
            aria-label="Draft production-order schedule"
          />
        </label>
      )}
      {term && pending && (
        <label className="block space-y-1 text-sm">
          <span className="font-medium">Meaning, in your words</span>
          <Textarea
            className="min-h-16 text-sm"
            value={meaning ?? draftMeaning}
            readOnly={!canEdit}
            onChange={(event) => setMeaning(event.target.value)}
            aria-label="Meaning, in your words"
          />
        </label>
      )}
      {pending ? (
        <ProposalReview
          caseId={caseId}
          citations={cites}
          citationLabels={labels}
          model={item.proposal.model}
          forName={item.proposal.for_name}
          canEdit={canEdit}
          acceptLabel={lead ? "Accept: add the finding and the task" : term ? "Confirm this meaning" : "Accept"}
          acceptBlocked={lead && !due ? "Set the task's due date to accept." : null}
          acceptExtra={
            lead ? (
              <label className="flex items-center gap-2 text-sm">
                Task due
                <Input type="date" className="h-8 w-44" value={due} onChange={(event) => setDue(event.target.value)} />
              </label>
            ) : null
          }
          onOpened={(citation) => agentProposalOpened(caseId, item.id, citation)}
          onAccept={() => acceptAgentProposal(caseId, item.id, acceptBody()).then(refresh)}
          onReject={(reason) => rejectAgentProposal(caseId, item.id, reason).then(refresh)}
        />
      ) : (
        <p className="text-sm" data-testid="agent-proposal-outcome">
          {item.review_status === "accepted" ? "Accepted" : "Rejected"}
          {item.reviewed_at ? ` on ${item.reviewed_at.slice(0, 10)}` : ""}.{" "}
          {item.proposal.review?.source_opened === true
            ? "A cited source was opened first."
            : item.proposal.review?.source_opened === false
              ? "Decided without opening a cited source (recorded through the API)."
              : ""}
        </p>
      )}
    </li>
  )
}

/** The case agent's drafted Workspace work: nothing is in the Workspace until a person accepts it. */
export function AgentProposalsPanel({ caseId, canEdit }: { caseId: string; canEdit: boolean }) {
  const [status, setStatus] = useState<string>("pending_review")
  const [offset, setOffset] = useState(0)
  const query = useQuery({
    queryKey: [...agentProposalKeys.list(caseId, status), offset],
    queryFn: () => listAgentProposals(caseId, status, offset),
  })
  return (
    <section className="space-y-3" aria-label="Proposals from the case agent">
      <div>
        <h2 className="text-base font-semibold">Proposals from the case agent</h2>
        <p className="text-sm text-muted-foreground">
          Drafts the case agent made when asked. None of them is in the Workspace until a person opens a cited source and
          accepts it.
        </p>
      </div>
      <div className="flex flex-wrap gap-2" role="group" aria-label="Show">
        {STATUSES.map(([value, label]) => (
          <Button
            key={value}
            size="sm"
            variant={status === value ? "primary" : "outline"}
            aria-pressed={status === value}
            onClick={() => {
              setStatus(value)
              setOffset(0)
            }}
          >
            {label}
          </Button>
        ))}
      </div>
      {status === "pending_review" && query.data?.order_rule && query.data.items.some((i) => i.order_reason) && (
        <p className="text-xs text-muted-foreground" data-testid="proposal-order-rule">{query.data.order_rule}</p>
      )}
      {query.isPending ? (
        <p role="status">Loading proposals…</p>
      ) : query.isError ? (
        <p role="alert">{query.error.message}</p>
      ) : !query.data.items.length ? (
        <p className="text-sm text-muted-foreground">No proposals here.</p>
      ) : (
        <>
          <p className="text-sm" data-testid="agent-proposals-count">
            Showing {offset + 1} to {offset + query.data.returned} of {query.data.total}.
          </p>
          <ul className="space-y-3">
            {query.data.items.map((item) => (
              <ProposalCard key={item.id} caseId={caseId} item={item} canEdit={canEdit} />
            ))}
          </ul>
          {offset > 0 && (
            <Button size="sm" variant="outline" onClick={() => setOffset(Math.max(0, offset - query.data.limit))}>
              Previous {query.data.limit}
            </Button>
          )}
          {query.data.total > offset + query.data.returned && (
            <Button size="sm" variant="outline" onClick={() => setOffset(offset + query.data.limit)}>
              Next {query.data.limit}
            </Button>
          )}
        </>
      )}
      <GlossaryPanel caseId={caseId} canEdit={canEdit} />
    </section>
  )
}
