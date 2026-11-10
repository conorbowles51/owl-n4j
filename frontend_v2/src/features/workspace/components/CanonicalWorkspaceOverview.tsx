import { useState, type ReactNode } from "react"
import { Link } from "react-router-dom"
import { toast } from "sonner"
import {
  AlertCircle,
  ArrowRight,
  Building2,
  CalendarClock,
  CheckCheck,
  ChevronDown,
  CircleDot,
  Clock3,
  FileText,
  FolderOpen,
  Lightbulb,
  Loader2,
  MapPin,
  Mic,
  Pin,
  ShieldCheck,
  Smartphone,
  UserRound,
  X,
  type LucideIcon,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { EmptyState } from "@/components/ui/empty-state"
import { LoadProgress } from "@/features/financial/components/LoadProgress"
import {
  DossierSourceViewer,
  type DossierSource,
} from "@/features/dossiers/components/DossierSourceViewer"
import { formatInterviewDate } from "@/features/dossiers/interview-date"
import {
  useSetAttentionState,
  useWorkspaceOverview,
} from "../hooks/use-workspace"
import type { WorkspaceAttentionItem, WorkspaceOverviewResponse } from "../api"
import { CaseBriefPanel } from "./CaseBriefPanel"
import { AssignedReviewsFeed } from "@/features/phones/ContinueReading"

interface Props {
  caseId: string
  caseName?: string
  canEdit: boolean
  onOpenCasework?: () => void
}

const dateFormat = new Intl.DateTimeFormat(undefined, {
  day: "numeric",
  month: "short",
})
function dateLabel(value?: string | null) {
  if (!value) return null
  // Deadlines are calendar dates, never midnight UTC shifted into the previous day.
  const date = new Date(
    /^\d{4}-\d{2}-\d{2}$/.test(value) ? `${value}T12:00:00` : value
  )
  return Number.isNaN(date.getTime()) ? null : dateFormat.format(date)
}

const entryKinds = {
  note: { label: "Note", plural: "Notes", icon: FileText },
  finding: { label: "Finding", plural: "Findings", icon: ShieldCheck },
  theory: { label: "Theory", plural: "Theories", icon: Lightbulb },
}
const subjectIcons: Record<string, LucideIcon> = {
  person: UserRound,
  organisation: Building2,
  organization: Building2,
  company: Building2,
  location: MapPin,
  device: Smartphone,
  event: CalendarClock,
}
const rowClass =
  "group flex min-h-12 w-full items-center gap-3 rounded-md py-3 text-left outline-none transition-colors hover:bg-muted/40 focus-visible:ring-2 focus-visible:ring-ring"

function Section({
  title,
  description,
  action,
  children,
  className = "",
}: {
  title: string
  description?: string
  action?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section aria-label={title} className={`min-w-0 ${className}`}>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
        <div>
          <h2 className="text-sm font-semibold tracking-tight">{title}</h2>
          {description && (
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
              {description}
            </p>
          )}
        </div>
        {action}
      </div>
      {children}
    </section>
  )
}

function ViewLink({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link
      to={to}
      className="inline-flex min-h-10 shrink-0 items-center gap-1.5 rounded-sm text-xs font-medium text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
    >
      {children}
      <ArrowRight aria-hidden="true" className="size-3.5" />
    </Link>
  )
}

function AttentionList({
  items,
  personal = false,
  onState,
  pending,
}: {
  items: WorkspaceAttentionItem[]
  personal?: boolean
  onState?: (item: WorkspaceAttentionItem, action: "dismiss" | "snooze") => void
  pending?: string
}) {
  const [expanded, setExpanded] = useState(false)
  const shown = expanded ? items : items.slice(0, 4)
  if (!items.length)
    return (
      <div className="flex items-center gap-3 py-6 text-sm text-muted-foreground">
        <CheckCheck
          aria-hidden="true"
          className="size-5 text-emerald-600 dark:text-emerald-400"
        />
        <div>
          <p className="font-medium text-foreground">
            {personal
              ? "No task reminders"
              : "Nothing critical needs attention"}
          </p>
          <p className="mt-1 text-xs">
            {personal
              ? "Assignments and reviews will appear here."
              : "Important case changes will appear here."}
          </p>
        </div>
      </div>
    )
  return (
    <>
      <ul className="divide-y divide-border/60">
        {shown.map((item) => {
          const action = item.metadata?.action as
            | { label?: unknown; href?: unknown }
            | undefined
          const isAction =
            typeof action?.label === "string" &&
            typeof action.href === "string" &&
            action.href.startsWith("/") &&
            !action.href.startsWith("//")
          return (
            <li key={item.attention_key} className="flex gap-2 py-3">
              <span
                aria-hidden="true"
                className={`mt-2 size-1.5 shrink-0 rounded-full ${item.priority_band === 0 ? "bg-rose-500" : item.priority_band === 1 ? "bg-amber-500" : "bg-muted-foreground/40"}`}
              />
              <div className="min-w-0 flex-1">
                <Link
                  to={item.href}
                  className="block rounded-sm py-1 text-sm font-medium outline-none hover:text-primary focus-visible:ring-2 focus-visible:ring-ring [overflow-wrap:anywhere]"
                >
                  {item.title}
                </Link>
                <p className="text-xs leading-relaxed text-muted-foreground">
                  {item.reason_label}
                  {item.due_at
                    ? ` · Due ${dateLabel(item.source_type === "deadline" ? item.due_at.slice(0, 10) : item.due_at)}`
                    : ""}
                </p>
                {item.summary && (
                  <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-muted-foreground">
                    {item.summary}
                  </p>
                )}
                {isAction && (
                  <ViewLink to={action!.href as string}>
                    {action!.label as string}
                  </ViewLink>
                )}
              </div>
              {personal && (
                <div className="flex shrink-0 self-start">
                  <Button
                    variant="ghost"
                    className="size-10 p-0 text-muted-foreground"
                    disabled={!!pending}
                    onClick={() => onState?.(item, "snooze")}
                    aria-label={`Snooze ${item.title} for one day`}
                    title="Snooze for one day"
                  >
                    {pending === item.attention_key ? (
                      <Loader2 className="size-4 animate-spin" />
                    ) : (
                      <Clock3 className="size-4" />
                    )}
                  </Button>
                  <Button
                    variant="ghost"
                    className="size-10 p-0 text-muted-foreground"
                    disabled={!!pending}
                    onClick={() => onState?.(item, "dismiss")}
                    aria-label={`Dismiss ${item.title}`}
                    title="Hide this reminder until it changes. This does not complete the work."
                  >
                    <X className="size-4" />
                  </Button>
                </div>
              )}
            </li>
          )
        })}
      </ul>
      {items.length > 4 && (
        <Button
          variant="ghost"
          className="mt-2 h-10 text-xs"
          onClick={() => setExpanded((value) => !value)}
          aria-expanded={expanded}
        >
          {expanded ? "Show less" : `Show ${items.length - 4} more reminders`}
        </Button>
      )}
    </>
  )
}

function RecentCasework({
  data,
  caseId,
}: {
  data: WorkspaceOverviewResponse
  caseId: string
}) {
  const entries = data.recent_casework.slice(0, 3)
  return (
    <Section
      title="Casework"
      description="What the team is recording and establishing."
      action={
        <ViewLink to={`/cases/${caseId}/workspace?view=casework`}>
          All casework
        </ViewLink>
      }
    >
      <nav aria-label="Casework types" className="mb-2 flex flex-wrap gap-x-5">
        {Object.entries(entryKinds).map(([kind, value]) => (
          <Link
            key={kind}
            aria-label={`${value.plural}${data.casework_by_type?.[kind as keyof typeof entryKinds] ? ` ${data.casework_by_type[kind as keyof typeof entryKinds].total}` : ""}`}
            to={`/cases/${caseId}/workspace?view=casework&kind=${kind}`}
            className="flex min-h-10 items-center gap-2 rounded-sm text-xs text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
          >
            <value.icon className="size-3.5" aria-hidden="true" />
            {value.plural}
            {data.casework_by_type?.[kind as keyof typeof entryKinds] && (
              <span className="font-medium tabular-nums text-foreground">
                {data.casework_by_type[kind as keyof typeof entryKinds].total}
              </span>
            )}
          </Link>
        ))}
      </nav>
      {entries.length ? (
        <ul className="divide-y divide-border/60">
          {entries.map((entry) => {
            const kind = entryKinds[entry.entry_type]
            return (
              <li key={entry.id}>
                <Link to={entry.href} className={rowClass}>
                  <kind.icon
                    aria-hidden="true"
                    className="size-4 shrink-0 text-muted-foreground"
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium">
                      {entry.title}
                    </span>
                    <span className="mt-1 block truncate text-xs text-muted-foreground">
                      {kind.label}
                      {entry.summary ? ` · ${entry.summary}` : ""}
                    </span>
                  </span>
                  {entry.review_state === "pending" && (
                    <Badge variant="outline">Review</Badge>
                  )}
                  <ArrowRight
                    className="size-3.5 shrink-0 text-muted-foreground"
                    aria-hidden="true"
                  />
                </Link>
              </li>
            )
          })}
        </ul>
      ) : (
        <p className="py-4 text-sm text-muted-foreground">
          Collect notes, record findings and test theories as the case develops.
        </p>
      )}
    </Section>
  )
}

export function CanonicalWorkspaceOverview({
  caseId,
  caseName,
  canEdit,
}: Props) {
  const overview = useWorkspaceOverview(caseId)
  const attention = useSetAttentionState(caseId)
  const [pending, setPending] = useState<string>()
  const [source, setSource] = useState<DossierSource | null>(null)
  const [showBrief, setShowBrief] = useState(false)
  const [showAllPins, setShowAllPins] = useState(false)
  const handleAttention = async (
    item: WorkspaceAttentionItem,
    action: "dismiss" | "snooze"
  ) => {
    setPending(item.attention_key)
    try {
      await attention.mutateAsync({
        attentionKey: item.attention_key,
        action,
        snoozedUntil:
          action === "snooze"
            ? new Date(Date.now() + 86_400_000).toISOString()
            : undefined,
      })
      toast.success(
        action === "dismiss"
          ? "Reminder dismissed. Work status unchanged."
          : "Reminder snoozed for one day"
      )
    } catch (error) {
      toast.error(
        error instanceof Error
          ? error.message
          : "Could not update this reminder. Try again."
      )
    } finally {
      setPending(undefined)
    }
  }
  if (overview.isLoading)
    return (
      <div className="flex min-h-96 items-center justify-center">
        <LoadProgress caseId={caseId} page="case/workspace" />
      </div>
    )
  if (overview.isError || !overview.data)
    return (
      <div className="mx-auto max-w-3xl p-8">
        <EmptyState
          icon={AlertCircle}
          title="Workspace overview unavailable"
          description="Your casework is still available in the other tabs."
          action={
            <Button variant="outline" onClick={() => void overview.refetch()}>
              Try again
            </Button>
          }
        />
      </div>
    )
  const data = overview.data
  const work = data.upcoming_work
  const pins = showAllPins
    ? data.pinned_evidence
    : data.pinned_evidence.slice(0, 4)
  const workHref = `/cases/${caseId}/workspace?view=work`
  return (
    <div className="mx-auto w-full max-w-[1200px] px-5 py-8 sm:px-9 sm:py-10 lg:px-12">
      <header className="mb-9">
        <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
          Case workspace
        </p>
        <h1 className="mt-2 font-display text-2xl font-semibold tracking-tight sm:text-3xl [overflow-wrap:anywhere]">
          {caseName || "Case overview"}
        </h1>
        {data.context.case_summary && (
          <p className="mt-3 max-w-2xl text-sm leading-relaxed text-muted-foreground">
            {data.context.case_summary}
          </p>
        )}
        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
          {data.context.investigation_type && (
            <span>{data.context.investigation_type}</span>
          )}
          {data.context.jurisdiction && (
            <span className="inline-flex items-center gap-1">
              <MapPin className="size-3" />
              {data.context.jurisdiction}
            </span>
          )}
          <ViewLink to={`/cases/${caseId}/workspace?view=setup`}>
            {canEdit ? "Case setup" : "Case context"}
          </ViewLink>
        </div>
        {data.context.mandate?.objective && (
          <div className="mt-4 max-w-3xl border-l-2 border-primary/40 pl-4">
            <p className="text-[10px] font-semibold uppercase tracking-[0.13em] text-muted-foreground">
              Objective
            </p>
            <p className="mt-1 text-sm leading-relaxed">
              {data.context.mandate.objective}
            </p>
          </div>
        )}
      </header>

      <div className="grid items-start gap-x-12 gap-y-9 lg:grid-cols-[minmax(0,1.5fr)_minmax(260px,1fr)]">
        <div className="min-w-0 space-y-8">
          <Section
            title="Your work"
            description="Assignments and reviews that need your attention."
            action={<ViewLink to={workHref}>Tasks & deadlines</ViewLink>}
          >
            <AttentionList
              items={data.personal_attention}
              personal
              pending={pending}
              onState={(item, action) => void handleAttention(item, action)}
            />
            <AssignedReviewsFeed caseId={caseId} />
          </Section>
          <div className="border-t border-border/70 pt-6">
            <RecentCasework data={data} caseId={caseId} />
          </div>
          {!!data.shared_attention.length && (
            <Section
              title="Case right now"
              className="border-t border-border/70 pt-6"
              description="Important changes for the whole team."
            >
              <AttentionList items={data.shared_attention} />
            </Section>
          )}
          <Section
            title="Pinned evidence"
            className="border-t border-border/70 pt-6"
            action={
              <ViewLink to={`/cases/${caseId}/evidence`}>Evidence</ViewLink>
            }
          >
            {pins.length ? (
              <ul className="divide-y divide-border/60">
                {pins.map((item) => (
                  <li key={item.id}>
                    <button
                      type="button"
                      className={rowClass}
                      onClick={() =>
                        setSource({
                          evidenceId: item.evidence_file_id || item.item_id,
                          name:
                            item.display_name ||
                            item.filename ||
                            "Pinned evidence",
                        })
                      }
                    >
                      <Pin
                        className="size-4 shrink-0 text-muted-foreground"
                        aria-hidden="true"
                      />
                      <span className="min-w-0 flex-1 truncate text-sm">
                        {item.display_name ||
                          item.filename ||
                          "Pinned evidence"}
                      </span>
                      <FolderOpen
                        className="size-4 shrink-0 text-muted-foreground"
                        aria-hidden="true"
                      />
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="py-3 text-xs leading-relaxed text-muted-foreground">
                Pin useful sources from Evidence to keep them close to your
                casework.
              </p>
            )}
            {data.pinned_evidence.length > 4 && (
              <Button
                variant="ghost"
                className="h-10 text-xs"
                onClick={() => setShowAllPins((value) => !value)}
                aria-expanded={showAllPins}
              >
                {showAllPins
                  ? "Show fewer sources"
                  : `Show ${data.pinned_evidence.length - 4} more sources`}
              </Button>
            )}
          </Section>
        </div>

        <aside className="min-w-0 space-y-8 lg:border-l lg:border-border/70 lg:pl-8">
          <Section
            title="Next up"
            action={<ViewLink to={workHref}>View all</ViewLink>}
          >
            {!!work?.past_deadline_total && (
              <Link
                to={workHref}
                className="mb-3 inline-flex min-h-10 items-center gap-2 text-xs font-medium text-rose-600 dark:text-rose-400"
              >
                <AlertCircle className="size-3.5" />
                {work.past_deadline_total} overdue deadline
                {work.past_deadline_total === 1 ? "" : "s"}
                <ArrowRight className="size-3" />
              </Link>
            )}
            {work?.deadlines.length ? (
              <ul className="divide-y divide-border/60">
                {work.deadlines.slice(0, 3).map((item) => (
                  <li key={item.id}>
                    <Link to={item.href} className={rowClass}>
                      <CalendarClock
                        className="size-4 shrink-0 text-muted-foreground"
                        aria-hidden="true"
                      />
                      <span className="min-w-0 flex-1 truncate text-sm">
                        {item.name}
                      </span>
                      <time
                        dateTime={item.due_date}
                        className="shrink-0 text-xs tabular-nums text-muted-foreground"
                      >
                        {dateLabel(item.due_date)}
                      </time>
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="py-3 text-xs text-muted-foreground">
                {work
                  ? "No upcoming deadlines."
                  : "Open tasks & deadlines for the full schedule."}
              </p>
            )}
            {!!work?.open_task_total && (
              <Link
                to={workHref}
                className="mt-1 flex min-h-10 items-center gap-2 text-xs text-muted-foreground hover:text-foreground"
              >
                <CheckCheck className="size-4" />
                {work.open_task_total} open task
                {work.open_task_total === 1 ? "" : "s"}
                <ArrowRight className="ml-auto size-3.5" />
              </Link>
            )}
            {work &&
              work.upcoming_deadline_total >
                Math.min(3, work.deadlines.length) && (
                <p className="text-xs text-muted-foreground">
                  Showing the next {Math.min(3, work.deadlines.length)} of{" "}
                  {work.upcoming_deadline_total} deadlines.
                </p>
              )}
          </Section>
          <Section
            title="Dossiers"
            description="The subjects at the centre of the case."
            className="border-t border-border/70 pt-6"
            action={
              <ViewLink to={`/cases/${caseId}/dossiers`}>All dossiers</ViewLink>
            }
          >
            {data.dossier_highlights.length ? (
              <ul className="divide-y divide-border/60">
                {data.dossier_highlights.slice(0, 5).map((item) => {
                  const Icon =
                    subjectIcons[item.dossier_type.toLowerCase()] || CircleDot
                  return (
                    <li key={item.id}>
                      <Link to={item.href} className={rowClass}>
                        <span className="grid size-8 shrink-0 place-items-center rounded-md bg-muted/60">
                          <Icon
                            className="size-4 text-muted-foreground"
                            aria-hidden="true"
                          />
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm font-medium">
                            {item.display_name}
                          </span>
                          <span className="mt-0.5 block truncate text-xs text-muted-foreground">
                            {item.needs_link_review
                              ? "Entity link needs review"
                              : item.summary ||
                                item.dossier_type.replace(/_/g, " ")}
                          </span>
                        </span>
                        <ArrowRight
                          className="size-3 shrink-0 text-muted-foreground"
                          aria-hidden="true"
                        />
                      </Link>
                    </li>
                  )
                })}
              </ul>
            ) : (
              <p className="py-3 text-xs leading-relaxed text-muted-foreground">
                Bring evidence and casework together around a person,
                organisation or other subject.
              </p>
            )}
          </Section>
          {!!data.interviews?.length && (
            <Section
              title="Interviews & statements"
              className="border-t border-border/70 pt-6"
              action={
                <ViewLink to={`/cases/${caseId}/dossiers`}>Dossiers</ViewLink>
              }
            >
              <ul className="divide-y divide-border/60">
                {data.interviews.slice(0, 2).map((item) => (
                  <li key={item.id}>
                    <Link to={item.href} className={rowClass}>
                      <Mic className="size-4 shrink-0 text-muted-foreground" />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm">
                          {item.dossier_name}
                        </span>
                        <span className="mt-1 block text-xs text-muted-foreground">
                          {[
                            formatInterviewDate(
                              item.date_value ?? item.interview_date
                            ),
                            item.status.replace(/_/g, " "),
                          ]
                            .filter(Boolean)
                            .join(" · ")}
                        </span>
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            </Section>
          )}
        </aside>
      </div>
      <div className="mt-9 border-t border-border/70 pt-3">
        <Button
          variant="ghost"
          className="h-11 gap-2 px-0 text-xs text-muted-foreground"
          onClick={() => setShowBrief((value) => !value)}
          aria-expanded={showBrief}
          aria-controls="workspace-change-brief"
        >
          <Clock3 className="size-4" />
          What changed
          <ChevronDown
            className={`size-3.5 transition-transform ${showBrief ? "rotate-180" : ""}`}
          />
        </Button>
        {showBrief && (
          <div id="workspace-change-brief" className="mt-3">
            <CaseBriefPanel caseId={caseId} canEdit={canEdit} />
          </div>
        )}
      </div>
      {source && (
        <DossierSourceViewer
          caseId={caseId}
          source={source}
          onClose={() => setSource(null)}
        />
      )}
    </div>
  )
}
