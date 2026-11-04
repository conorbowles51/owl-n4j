import { LoadProgress } from "@/features/financial/components/LoadProgress"
import { useEffect, useState, type ReactNode } from "react"
import { Link, useNavigate } from "react-router-dom"
import { toast } from "sonner"
import {
  AlertCircle,
  ArrowRight,
  BookOpenCheck,
  CalendarClock,
  CheckCircle2,
  Clock3,
  ContactRound,
  FileText,
  FolderKanban,
  Loader2,
  MapPin,
  PauseCircle,
  PencilLine,
  Pin,
  ShieldAlert,
  UserRoundCheck,
  Camera,
  Lightbulb,
  ListChecks,
  Mic,
  Network,
  ShieldCheck,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { HowThisWasFound } from "./HowThisWasFound"
import { Button } from "@/components/ui/button"
import { EmptyState } from "@/components/ui/empty-state"
import { cn } from "@/lib/cn"
import type { WorkspaceAttentionItem, WorkspaceOverviewResponse } from "../api"
import { splitParticipants } from "@/features/dossiers/interview-participants"
import { formatInterviewDate } from "@/features/dossiers/interview-date"
import {
  useSetAttentionState,
  useWorkspaceOverview,
} from "../hooks/use-workspace"
import { DossierSourceViewer, type DossierSource } from "@/features/dossiers/components/DossierSourceViewer"
import { CaseContextSection } from "./CaseContextSection"
import { CaseBriefPanel } from "./CaseBriefPanel"
import { SnapshotsSection } from "@/features/cases/components/SnapshotsSection"
import { CaseFileSummaries } from "./CaseFileSummaries"

interface CanonicalWorkspaceOverviewProps {
  caseId: string
  /** Kept for callers; each casework section now links to its own Casework tab. */
  onOpenCasework?: () => void
  canEdit: boolean
  onDirtyChange?: (dirty: boolean) => void
}

const dateTimeFormatter = new Intl.DateTimeFormat(undefined, {
  dateStyle: "medium",
  timeStyle: "short",
})

const dateFormatter = new Intl.DateTimeFormat(undefined, {
  dateStyle: "medium",
})

function formatDate(value: string | null | undefined, dateOnly = false) {
  if (!value) return null
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return null
  return (dateOnly ? dateFormatter : dateTimeFormatter).format(date)
}

/** A next step the item names itself (a phone that is ready opens its summary, 07 J-1 step 4). */
function attentionAction(item: WorkspaceAttentionItem): { label: string; href: string } | null {
  const a = item.metadata?.action as { label?: unknown; href?: unknown } | undefined
  return a && typeof a.label === "string" && typeof a.href === "string" && a.href.startsWith("/") ? { label: a.label, href: a.href } : null
}

function attentionTone(priorityBand: number) {
  if (priorityBand === 0) {
    return "border-rose-200 bg-rose-50/55 text-rose-700 dark:border-rose-900/70 dark:bg-rose-950/20 dark:text-rose-300"
  }
  if (priorityBand === 1) {
    return "border-status-warning/50 bg-status-warning-soft text-status-warning"
  }
  if (priorityBand === 2) {
    return "border-violet-200 bg-violet-50/55 text-violet-700 dark:border-violet-900/70 dark:bg-violet-950/20 dark:text-violet-300"
  }
  return "border-border bg-muted/30 text-muted-foreground"
}

function AttentionList({
  items,
  personal,
  onOpen,
  onDismiss,
  onSnooze,
  pendingKey,
}: {
  items: WorkspaceAttentionItem[]
  personal: boolean
  onOpen: (item: WorkspaceAttentionItem) => void
  onDismiss?: (item: WorkspaceAttentionItem) => void
  onSnooze?: (item: WorkspaceAttentionItem) => void
  pendingKey?: string
}) {
  if (!items.length) {
    return (
      <EmptyState
        icon={personal ? UserRoundCheck : CheckCircle2}
        title={personal ? "You’re caught up" : "Nothing critical needs attention"}
        description={
          personal
            ? "Assigned work, drafts, and reviews awaiting you will appear here."
            : "Shared deadlines, urgent work, reviews, and material case changes will appear here."
        }
        className="py-10"
      />
    )
  }

  return (
    <div className="divide-y divide-border">
      {items.map((item) => {
        const due = formatDate(item.due_at, item.source_type === "deadline")
        const occurred = formatDate(item.occurred_at)
        const pending = pendingKey === item.attention_key
        const action = attentionAction(item)
        return (
          <article key={item.attention_key} className="px-4 py-3.5">
            <div className="flex items-start gap-3">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-1.5">
                  <Badge
                    variant="outline"
                    className={cn("h-5 text-[10px]", attentionTone(item.priority_band))}
                  >
                    {item.reason_label}
                  </Badge>
                  <span className="text-[10px] font-medium tabular-nums text-muted-foreground">
                    Priority {item.rank}
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => onOpen(item)}
                  className="group mt-1.5 block max-w-full text-left outline-none focus-visible:rounded-sm focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <span className="inline-flex max-w-full items-center gap-1 text-xs font-semibold text-foreground group-hover:text-primary">
                    <span className="truncate">{item.title}</span>
                    <ArrowRight className="size-3 shrink-0 opacity-0 transition-opacity group-hover:opacity-100" />
                  </span>
                </button>
                {item.summary ? (
                  <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-muted-foreground">
                    {item.summary}
                  </p>
                ) : null}
                {action ? (
                  <Link to={action.href} className="mt-1 inline-block text-xs font-medium underline underline-offset-2">
                    {action.label}
                  </Link>
                ) : null}
                {due || occurred ? (
                  <p className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-muted-foreground">
                    {due ? (
                      <span className="inline-flex items-center gap-1">
                        <CalendarClock className="size-3" /> Due {due}
                      </span>
                    ) : null}
                    {occurred && !due ? (
                      <span className="inline-flex items-center gap-1">
                        <Clock3 className="size-3" /> Updated {occurred}
                      </span>
                    ) : null}
                  </p>
                ) : null}
              </div>

              {personal ? (
                <div className="flex shrink-0 items-center gap-1">
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    disabled={pending}
                    onClick={() => onSnooze?.(item)}
                    aria-label={`Snooze ${item.title} for one day`}
                    title="Snooze for one day"
                  >
                    {pending ? <Loader2 className="size-3.5 animate-spin" /> : <PauseCircle className="size-3.5" />}
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    disabled={pending}
                    onClick={() => onDismiss?.(item)}
                    aria-label={`Dismiss ${item.title}`}
                    title="Dismiss until this item changes"
                  >
                    <CheckCircle2 className="size-3.5" />
                  </Button>
                </div>
              ) : null}
            </div>
          </article>
        )
      })}
    </div>
  )
}

type CaseworkKind = "finding" | "theory" | "note"
type CaseworkSectionData = { entries: WorkspaceOverviewResponse["recent_casework"]; total: number | null }
type Navigate = (to: string) => void

/** A kind's own entries; a server without the per-kind lists falls back to the mixed recent list (total unknown). */
function caseworkSection(data: WorkspaceOverviewResponse, kind: CaseworkKind): CaseworkSectionData {
  const own = data.casework_by_type?.[kind]
  if (own) return { entries: own.entries, total: own.total }
  return { entries: data.recent_casework.filter((entry) => entry.entry_type === kind), total: null }
}

function shownOf(shown: number, total: number | null, noun: string) {
  if (total === null) return `${shown} recent ${noun}`
  return shown < total ? `Newest ${shown} of ${total} ${noun}` : `${total} ${noun}`
}

function SectionHeader({ icon: Icon, heading, description, action }: {
  icon: typeof FileText
  heading: string
  description: string
  action?: ReactNode
}) {
  return (
    <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-3">
      <div className="min-w-0">
        <div className="flex items-center gap-2"><Icon className="size-4 text-muted-foreground" /><h2 className="text-sm font-semibold">{heading}</h2></div>
        <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>
      </div>
      {action}
    </div>
  )
}

const KIND_NOUN: Record<CaseworkKind, [string, string]> = {
  finding: ["finding", "findings"],
  theory: ["theory", "theories"],
  note: ["note", "notes"],
}

function CaseworkSection({ caseId, kind, heading, icon, description, section, onNavigate }: {
  caseId: string
  kind: CaseworkKind
  heading: string
  icon: typeof FileText
  description: string
  section: CaseworkSectionData
  onNavigate: Navigate
}) {
  const [one, many] = KIND_NOUN[kind]
  return (
    <section className="overflow-hidden rounded-xl border border-border bg-card shadow-sm" aria-label={heading} data-testid={`workspace-section-${kind}`}>
      <SectionHeader
        icon={icon}
        heading={heading}
        description={`${description} ${shownOf(section.entries.length, section.total, section.total === 1 ? one : many)}.`}
        action={<Button type="button" variant="ghost" size="sm" aria-label={`View all ${many}`} onClick={() => onNavigate(`/cases/${caseId}/workspace?view=casework&kind=${kind}`)}>View all</Button>}
      />
      {section.entries.length ? (
        <div className="divide-y divide-border">
          {section.entries.map((entry) => (
            <div key={entry.id}>
              <button type="button" onClick={() => onNavigate(entry.href)} className="grid w-full gap-2 px-4 py-3 text-left hover:bg-muted/25 sm:grid-cols-[minmax(0,1fr)_auto]">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="min-w-0 truncate text-xs font-semibold">{entry.title}</span>
                    {entry.review_state === "pending" ? <Badge variant="warning">Review</Badge> : null}
                  </div>
                  {entry.summary ? <p className="mt-1 line-clamp-1 text-xs text-muted-foreground">{entry.summary}</p> : null}
                </div>
                {entry.updated_at ? <span className="flex items-center gap-1 self-center text-[10px] text-muted-foreground"><Clock3 className="size-3" />{formatDate(entry.updated_at)}</span> : null}
              </button>
              {entry.entry_type === "finding" ? <HowThisWasFound caseId={caseId} entryId={entry.id} /> : null}
            </div>
          ))}
        </div>
      ) : (
        <EmptyState icon={icon} title={`No ${many} yet`} description={`${heading} will appear here as the investigation develops.`} className="py-8" />
      )}
    </section>
  )
}

function UpcomingWorkSection({ work, caseId, onNavigate }: {
  work: WorkspaceOverviewResponse["upcoming_work"]
  caseId: string
  onNavigate: Navigate
}) {
  const openDeadlines = () => onNavigate(`/cases/${caseId}/workspace?view=work`)
  const counts = work
    ? [
        `${work.upcoming_deadline_total} upcoming deadline${work.upcoming_deadline_total === 1 ? "" : "s"}`,
        work.past_deadline_total ? `${work.past_deadline_total} past` : null,
        `${work.open_task_total} open task${work.open_task_total === 1 ? "" : "s"}`,
      ].filter(Boolean).join(" · ")
    : "Open the Deadlines tab for the case's deadlines and tasks"
  return (
    <section className="overflow-hidden rounded-xl border border-border bg-card shadow-sm" aria-label="Case deadlines and tasks" data-testid="workspace-section-work">
      <SectionHeader
        icon={CalendarClock}
        heading="Case deadlines and tasks"
        description={`The next items, soonest first. ${counts}.`}
        action={<Button type="button" variant="ghost" size="sm" onClick={openDeadlines}>All deadlines and tasks</Button>}
      />
      {work && (work.deadlines.length || work.tasks.length) ? (
        <div className="grid gap-px bg-border md:grid-cols-2">
          <div className="bg-card">
            <p className="px-4 pt-3 text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
              Next deadlines{work.deadlines.length < work.upcoming_deadline_total ? ` (${work.deadlines.length} of ${work.upcoming_deadline_total})` : ""}
            </p>
            {work.deadlines.length ? work.deadlines.map((d) => (
              <button key={d.id} type="button" onClick={() => onNavigate(d.href)} className="flex w-full items-center gap-2 px-4 py-2 text-left hover:bg-muted/25">
                <CalendarClock className="size-3.5 shrink-0 text-muted-foreground" />
                <span className="min-w-0 flex-1 truncate text-xs font-semibold">{d.name}</span>
                <span className="text-[10px] tabular-nums text-muted-foreground">{formatDate(`${d.due_date}T00:00:00`, true)}</span>
              </button>
            )) : <p className="px-4 py-2 text-xs text-muted-foreground">No upcoming deadlines.</p>}
          </div>
          <div className="bg-card">
            <p className="px-4 pt-3 text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
              Open tasks{work.tasks.length < work.open_task_total ? ` (${work.tasks.length} of ${work.open_task_total})` : ""}
            </p>
            {work.tasks.length ? work.tasks.map((t) => (
              <button key={t.id} type="button" onClick={() => onNavigate(t.href)} className="flex w-full items-center gap-2 px-4 py-2 text-left hover:bg-muted/25">
                <ListChecks className="size-3.5 shrink-0 text-muted-foreground" />
                <span className="min-w-0 flex-1 truncate text-xs font-semibold">{t.title}</span>
                {t.priority === "urgent" || t.priority === "high" ? <Badge variant="warning" className="capitalize">{t.priority}</Badge> : null}
                <span className="text-[10px] text-muted-foreground">{[t.assignee_name, t.due_at ? `Due ${formatDate(t.due_at, true)}` : null].filter(Boolean).join(" · ") || "No due date"}</span>
              </button>
            )) : <p className="px-4 py-2 text-xs text-muted-foreground">No open tasks.</p>}
          </div>
        </div>
      ) : work ? (
        <EmptyState icon={CalendarClock} title="Nothing scheduled" description="Upcoming deadlines and open tasks will appear here." className="py-8" />
      ) : null}
    </section>
  )
}

function InterviewsSection({ data, caseId, onNavigate }: {
  data: WorkspaceOverviewResponse
  caseId: string
  onNavigate: Navigate
}) {
  const items = data.interviews ?? []
  const total = data.interview_total ?? null
  return (
    <section className="overflow-hidden rounded-xl border border-border bg-card shadow-sm" aria-label="Witnesses: interviews and statements" data-testid="workspace-section-interviews">
      <SectionHeader
        icon={Mic}
        heading="Witnesses: interviews and statements"
        description={total === null ? "Recorded in each person's dossier." : `Recorded in each person's dossier. ${shownOf(items.length, total, total === 1 ? "interview or statement" : "interviews and statements")}.`}
        action={<Button type="button" variant="ghost" size="sm" onClick={() => onNavigate(`/cases/${caseId}/dossiers`)}>All Dossiers</Button>}
      />
      {items.length ? (
        <div className="divide-y divide-border">
          {items.map((item) => {
            const { names, interviewedBy } = splitParticipants(item.participants)
            return (
              <button key={item.id} type="button" onClick={() => onNavigate(item.href)} className="block w-full px-4 py-3 text-left hover:bg-muted/25">
                <div className="flex items-center gap-2">
                  <span className="min-w-0 flex-1 truncate text-xs font-semibold">{item.dossier_name}</span>
                  <Badge variant="outline" className="capitalize">{item.status.replace(/_/g, " ")}</Badge>
                </div>
                <p className="mt-0.5 text-[10px] text-muted-foreground">
                  {[formatInterviewDate(item.date_value ?? item.interview_date), names.length ? names.join(", ") : null, interviewedBy ? `Interviewed by ${interviewedBy}` : null].filter(Boolean).join(" · ")}
                </p>
                {item.summary ? <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{item.summary}</p> : null}
              </button>
            )
          })}
        </div>
      ) : (
        <EmptyState icon={Mic} title="No interviews or statements" description={total === null ? "Interviews and statements are recorded in each person's dossier." : "Interviews and statements recorded in a dossier will appear here."} className="py-8" />
      )}
    </section>
  )
}

export function CanonicalWorkspaceOverview({
  caseId,
  canEdit,
  onDirtyChange,
}: CanonicalWorkspaceOverviewProps) {
  const routerNavigate = useNavigate()
  const navigate = (to: string) => { if (!setupDirty || window.confirm("Discard your unsaved setup changes?")) routerNavigate(to) }
  const [source, setSource] = useState<DossierSource | null>(null)
  const [showContextEditor, setShowContextEditor] = useState(false)
  const [setupDirty, setSetupDirty] = useState(false)
  useEffect(() => { onDirtyChange?.(setupDirty); return () => onDirtyChange?.(false) }, [setupDirty, onDirtyChange])
  const [pendingAttentionKey, setPendingAttentionKey] = useState<string>()
  const overview = useWorkspaceOverview(caseId)
  const setAttentionState = useSetAttentionState(caseId)

  const handleAttentionState = async (
    item: WorkspaceAttentionItem,
    action: "dismiss" | "snooze",
  ) => {
    setPendingAttentionKey(item.attention_key)
    try {
      await setAttentionState.mutateAsync({
        attentionKey: item.attention_key,
        action,
        snoozedUntil:
          action === "snooze"
            ? new Date(Date.now() + 24 * 60 * 60 * 1_000).toISOString()
            : undefined,
      })
      toast.success(action === "dismiss" ? "Item dismissed" : "Item snoozed for one day")
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not update your attention list")
    } finally {
      setPendingAttentionKey(undefined)
    }
  }

  if (overview.isLoading) {
    return (
      <div className="flex min-h-96 items-center justify-center">
        <LoadProgress caseId={caseId} page="case/workspace" />
      </div>
    )
  }

  if (overview.isError || !overview.data) {
    return (
      <div className="mx-auto max-w-3xl p-5">
        <EmptyState
          icon={AlertCircle}
          title="Workspace overview unavailable"
          description={overview.error instanceof Error ? overview.error.message : "The case summary could not be loaded."}
          action={<Button variant="outline" onClick={() => overview.refetch()}>Try again</Button>}
        />
      </div>
    )
  }

  const data = overview.data
  const mandate = data.context.mandate

  return (
    <div className="mx-auto max-w-6xl space-y-5 p-4 sm:p-5">
      <UpcomingWorkSection work={data.upcoming_work} onNavigate={navigate} caseId={caseId} />

      <CaseworkSection
        caseId={caseId}
        kind="finding"
        heading="Findings"
        icon={ShieldCheck}
        description="Conclusions the team has recorded, with how each was found."
        section={caseworkSection(data, "finding")}
        onNavigate={navigate}
      />

      <div className="grid items-start gap-5 lg:grid-cols-2">
        <section className="overflow-hidden rounded-xl border border-border bg-card shadow-sm" aria-labelledby="case-right-now-heading">
          <div className="border-b border-border px-4 py-3">
            <div className="flex items-center gap-2">
              <ShieldAlert className="size-4 text-rose-500" />
              <h2 id="case-right-now-heading" className="text-sm font-semibold">Case right now</h2>
            </div>
            <p className="mt-0.5 text-xs text-muted-foreground">Shared facts and changes the whole team should have in view.</p>
          </div>
          <AttentionList
            items={data.shared_attention}
            personal={false}
            onOpen={(item) => navigate(item.href)}
          />
        </section>

        <section className="overflow-hidden rounded-xl border border-border bg-card shadow-sm" aria-labelledby="your-work-heading">
          <div className="border-b border-border px-4 py-3">
            <div className="flex items-center gap-2">
              <UserRoundCheck className="size-4 text-sky-600" />
              <h2 id="your-work-heading" className="text-sm font-semibold">Your work</h2>
            </div>
            <p className="mt-0.5 text-xs text-muted-foreground">Assignments, drafts, and reviews that need your attention.</p>
          </div>
          <AttentionList
            items={data.personal_attention}
            personal
            pendingKey={pendingAttentionKey}
            onOpen={(item) => navigate(item.href)}
            onDismiss={(item) => void handleAttentionState(item, "dismiss")}
            onSnooze={(item) => void handleAttentionState(item, "snooze")}
          />
        </section>
      </div>

      <CaseBriefPanel caseId={caseId} canEdit={canEdit} />

      <section className="relative overflow-hidden rounded-xl border border-border bg-card shadow-sm">
        <div className="pointer-events-none absolute inset-y-0 right-0 w-80 bg-[radial-gradient(circle_at_right,rgba(180,22,36,.08),transparent_68%)]" />
        <div className="relative grid gap-5 p-5 lg:grid-cols-[minmax(0,1.3fr)_minmax(280px,.7fr)]">
          <div>
            <div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.13em] text-muted-foreground">
              <BookOpenCheck className="size-3.5 text-brand-600" /> Client profile and exposure
            </div>
            <p className="mt-1 text-[10px] text-muted-foreground">Case summary and objective</p>
            <h1 className="mt-2 font-display text-lg font-semibold text-foreground">
              {data.context.case_summary || "Case context has not been summarised yet."}
            </h1>
            {data.context.background ? (
              <p className="mt-2 max-w-3xl text-xs leading-relaxed text-muted-foreground">
                {data.context.background}
              </p>
            ) : null}
            <div className="mt-3 flex flex-wrap gap-2">
              {data.context.investigation_type ? <Badge variant="outline">{data.context.investigation_type}</Badge> : null}
              {data.context.jurisdiction ? (
                <Badge variant="outline"><MapPin className="size-3" /> {data.context.jurisdiction}</Badge>
              ) : null}
              {canEdit ? (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => { if (!showContextEditor || !setupDirty || window.confirm("Discard your unsaved setup changes?")) setShowContextEditor((current) => !current) }}
                  aria-expanded={showContextEditor}
                >
                  <PencilLine className="size-3.5" />
                  {showContextEditor ? "Close setup" : "Edit case setup"}
                </Button>
              ) : null}
            </div>
          </div>

          <div className="rounded-lg border border-border/80 bg-background/75 p-4 backdrop-blur-sm">
            <div className="flex items-center justify-between gap-2">
              <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">Objective</p>
              <Badge variant={data.context.mandate_complete ? "success" : "warning"}>
                {data.context.mandate_complete ? `Version ${mandate?.version_number}` : "Not set"}
              </Badge>
            </div>
            <p className="mt-2 text-xs font-medium leading-relaxed text-foreground">
              {mandate?.objective || "Add what you want to establish so investigators and AI share the same objective."}
            </p>
            {mandate?.key_questions.length ? (
              <p className="mt-2 text-[11px] text-muted-foreground">
                {mandate.key_questions.length} key question{mandate.key_questions.length === 1 ? "" : "s"} in scope
              </p>
            ) : null}
          </div>
        </div>
      </section>

      {showContextEditor ? <CaseContextSection caseId={caseId} canEdit={canEdit} onDirtyChange={setSetupDirty} /> : null}

      <div className="grid items-start gap-5 lg:grid-cols-2">
        <CaseworkSection
          caseId={caseId}
          kind="theory"
          heading="Investigative theories"
          icon={Lightbulb}
          description="Working explanations the team is testing."
          section={caseworkSection(data, "theory")}
          onNavigate={navigate}
        />
        <CaseworkSection
          caseId={caseId}
          kind="note"
          heading="Notes"
          icon={FolderKanban}
          description="Investigator-authored notes, newest first."
          section={caseworkSection(data, "note")}
          onNavigate={navigate}
        />
      </div>

      <section className="overflow-hidden rounded-xl border border-border bg-card shadow-sm">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <div>
            <div className="flex items-center gap-2"><Camera className="size-4 text-muted-foreground" /><h2 className="text-sm font-semibold">Snapshots</h2></div>
            <p className="mt-0.5 text-xs text-muted-foreground">Your saved views of the graph for this case, each with a report of its own entities, events and sources.</p>
          </div>
          <Button type="button" variant="ghost" size="sm" onClick={() => navigate(`/cases/${caseId}/graph`)}>Open Graph</Button>
        </div>
        <div className="px-4 py-3"><SnapshotsSection caseId={caseId} canEdit={canEdit} /></div>
      </section>

      <div className="grid items-start gap-5 lg:grid-cols-2">
        <InterviewsSection data={data} onNavigate={navigate} caseId={caseId} />
      <section className="overflow-hidden rounded-xl border border-border bg-card shadow-sm">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <div>
            <div className="flex items-center gap-2"><ContactRound className="size-4 text-muted-foreground" /><h2 className="text-sm font-semibold">Entity summary</h2></div>
            <p className="mt-0.5 text-xs text-muted-foreground">Subjects the team has marked as important.</p>
          </div>
          <Button type="button" variant="ghost" size="sm" onClick={() => navigate(`/cases/${caseId}/dossiers`)}>All Dossiers</Button>
        </div>
        {data.dossier_highlights.length ? (
          <div className="divide-y divide-border">
            {data.dossier_highlights.map((dossier) => (
              <button key={dossier.id} type="button" onClick={() => navigate(dossier.href)} className="block w-full px-4 py-3 text-left hover:bg-muted/25">
                <div className="flex items-center gap-2">
                  <span className="min-w-0 flex-1 truncate text-xs font-semibold">{dossier.display_name}</span>
                  <Badge variant="outline" className="capitalize">{dossier.dossier_type}</Badge>
                  {dossier.needs_link_review ? <Badge variant="warning">Review link</Badge> : null}
                </div>
                {dossier.summary ? <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{dossier.summary}</p> : null}
              </button>
            ))}
          </div>
        ) : (
          <EmptyState icon={ContactRound} title="No entities highlighted" description="Important subjects will appear here once investigators begin curating Dossiers." className="py-10" />
        )}
      </section>
      </div>

      <section className="overflow-hidden rounded-xl border border-border bg-card shadow-sm">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <div>
            <div className="flex items-center gap-2"><Pin className="size-4 text-amber-500" /><h2 className="text-sm font-semibold">Pinned Evidence</h2></div>
            <p className="mt-0.5 text-xs text-muted-foreground">A small, shared selection curated from the canonical Evidence area.</p>
          </div>
          <Button type="button" variant="ghost" size="sm" onClick={() => navigate(`/cases/${caseId}/evidence`)}>Open Evidence</Button>
        </div>
        {data.pinned_evidence.length ? (
          <div className="grid gap-px bg-border sm:grid-cols-2 lg:grid-cols-3">
            {data.pinned_evidence.map((item) => (
              <button key={item.id} type="button" onClick={() => setSource({ evidenceId: item.evidence_file_id || item.item_id, name: item.display_name || item.filename || "Pinned evidence" })} className="flex min-w-0 items-center gap-3 bg-card px-4 py-3 text-left hover:bg-muted/25">
                <FileText className="size-4 shrink-0 text-muted-foreground" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-xs font-semibold">{item.display_name || item.filename || "Pinned evidence"}</span>
                  <span className="mt-0.5 block truncate text-[10px] text-muted-foreground">{item.pinned_by_name ? `Pinned by ${item.pinned_by_name}` : "Shared with the case team"}</span>
                </span>
              </button>
            ))}
          </div>
        ) : (
          <EmptyState icon={Pin} title="No pinned evidence" description="Pin selected material from Evidence to keep it in the team’s shared view." className="py-10" />
        )}
      </section>
      <section className="overflow-hidden rounded-xl border border-border bg-card shadow-sm">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <div>
            <div className="flex items-center gap-2"><FileText className="size-4 text-muted-foreground" /><h2 className="text-sm font-semibold">Case files</h2></div>
            <p className="mt-0.5 text-xs text-muted-foreground">Each file's AI summary, inline. Open a file to read it.</p>
          </div>
          <Button type="button" variant="ghost" size="sm" onClick={() => navigate(`/cases/${caseId}/evidence`)}>Open Evidence</Button>
        </div>
        <CaseFileSummaries caseId={caseId} onOpen={(file) => setSource({ evidenceId: file.id, name: file.original_filename })} />
      </section>

      <nav aria-label="Case views" className="flex flex-wrap items-center gap-2 rounded-xl border border-border bg-card px-4 py-3 shadow-sm">
        <span className="mr-1 text-xs font-semibold">Graph · Timeline · Map</span>
        <Button type="button" variant="outline" size="sm" onClick={() => navigate(`/cases/${caseId}/graph`)}><Network className="size-3.5" /> Open Graph</Button>
        <Button type="button" variant="outline" size="sm" onClick={() => navigate(`/cases/${caseId}/timeline`)}><Clock3 className="size-3.5" /> Open Timeline</Button>
        <Button type="button" variant="outline" size="sm" onClick={() => navigate(`/cases/${caseId}/map`)}><MapPin className="size-3.5" /> Open Map</Button>
      </nav>
      {source && <DossierSourceViewer caseId={caseId} source={source} onClose={() => setSource(null)} />}
    </div>
  )
}
