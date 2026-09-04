import { useState } from "react"
import { useNavigate } from "react-router-dom"
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
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { EmptyState } from "@/components/ui/empty-state"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { cn } from "@/lib/cn"
import type { WorkspaceAttentionItem } from "../api"
import {
  useSetAttentionState,
  useWorkspaceOverview,
} from "../hooks/use-workspace"
import { CaseContextSection } from "./CaseContextSection"

interface CanonicalWorkspaceOverviewProps {
  caseId: string
  onOpenCasework: () => void
  canEdit: boolean
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

function attentionTone(priorityBand: number) {
  if (priorityBand === 0) {
    return "border-rose-200 bg-rose-50/55 text-rose-700 dark:border-rose-900/70 dark:bg-rose-950/20 dark:text-rose-300"
  }
  if (priorityBand === 1) {
    return "border-amber-200 bg-amber-50/55 text-amber-700 dark:border-amber-900/70 dark:bg-amber-950/20 dark:text-amber-300"
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

export function CanonicalWorkspaceOverview({
  caseId,
  onOpenCasework,
  canEdit,
}: CanonicalWorkspaceOverviewProps) {
  const navigate = useNavigate()
  const [showContextEditor, setShowContextEditor] = useState(false)
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
        <LoadingSpinner size="lg" />
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
      <section className="relative overflow-hidden rounded-xl border border-border bg-card shadow-sm">
        <div className="pointer-events-none absolute inset-y-0 right-0 w-80 bg-[radial-gradient(circle_at_right,rgba(180,22,36,.08),transparent_68%)]" />
        <div className="relative grid gap-5 p-5 lg:grid-cols-[minmax(0,1.3fr)_minmax(280px,.7fr)]">
          <div>
            <div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.13em] text-muted-foreground">
              <BookOpenCheck className="size-3.5 text-brand-600" /> Case orientation
            </div>
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
                  onClick={() => setShowContextEditor((current) => !current)}
                  aria-expanded={showContextEditor}
                >
                  <PencilLine className="size-3.5" />
                  {showContextEditor ? "Close context editor" : "Manage context"}
                </Button>
              ) : null}
            </div>
          </div>

          <div className="rounded-lg border border-border/80 bg-background/75 p-4 backdrop-blur-sm">
            <div className="flex items-center justify-between gap-2">
              <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">Active mandate</p>
              <Badge variant={data.context.mandate_complete ? "success" : "warning"}>
                {data.context.mandate_complete ? `Version ${mandate?.version_number}` : "Incomplete"}
              </Badge>
            </div>
            <p className="mt-2 text-xs font-medium leading-relaxed text-foreground">
              {mandate?.objective || "Define the objective and key questions so investigators and AI work from the same brief."}
            </p>
            {mandate?.key_questions.length ? (
              <p className="mt-2 text-[11px] text-muted-foreground">
                {mandate.key_questions.length} key question{mandate.key_questions.length === 1 ? "" : "s"} in scope
              </p>
            ) : null}
          </div>
        </div>
      </section>

      {showContextEditor ? <CaseContextSection caseId={caseId} canEdit={canEdit} /> : null}

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

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1.2fr)_minmax(280px,.8fr)]">
        <section className="overflow-hidden rounded-xl border border-border bg-card shadow-sm">
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <div>
              <div className="flex items-center gap-2"><FolderKanban className="size-4 text-muted-foreground" /><h2 className="text-sm font-semibold">Recent casework</h2></div>
              <p className="mt-0.5 text-xs text-muted-foreground">Selective investigator-authored work, not another evidence list.</p>
            </div>
            <Button type="button" variant="ghost" size="sm" onClick={onOpenCasework}>View casework</Button>
          </div>
          {data.recent_casework.length ? (
            <div className="divide-y divide-border">
              {data.recent_casework.map((entry) => (
                <button key={entry.id} type="button" onClick={() => navigate(entry.href)} className="grid w-full gap-2 px-4 py-3 text-left hover:bg-muted/25 sm:grid-cols-[minmax(0,1fr)_auto]">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Badge variant="outline" className="capitalize">{entry.entry_type}</Badge>
                      <span className="min-w-0 truncate text-xs font-semibold">{entry.title}</span>
                      {entry.review_state === "pending" ? <Badge variant="warning">Review</Badge> : null}
                    </div>
                    {entry.summary ? <p className="mt-1 line-clamp-1 text-xs text-muted-foreground">{entry.summary}</p> : null}
                  </div>
                  {entry.updated_at ? <span className="flex items-center gap-1 self-center text-[10px] text-muted-foreground"><Clock3 className="size-3" />{formatDate(entry.updated_at)}</span> : null}
                </button>
              ))}
            </div>
          ) : (
            <EmptyState icon={FolderKanban} title="No casework yet" description="Notes, Findings, and Theories will appear here as the investigation develops." className="py-10" />
          )}
        </section>

        <section className="overflow-hidden rounded-xl border border-border bg-card shadow-sm">
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <div>
              <div className="flex items-center gap-2"><ContactRound className="size-4 text-muted-foreground" /><h2 className="text-sm font-semibold">Dossier highlights</h2></div>
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
            <EmptyState icon={ContactRound} title="No Dossier highlights" description="Important subjects will appear here once investigators begin curating Dossiers." className="py-10" />
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
              <button key={item.id} type="button" onClick={() => navigate(`/cases/${caseId}/evidence`)} className="flex min-w-0 items-center gap-3 bg-card px-4 py-3 text-left hover:bg-muted/25">
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
    </div>
  )
}
