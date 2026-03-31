import {
  Lightbulb,
  CheckSquare,
  Users,
  StickyNote,
  FileText,
  Paperclip,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { ConfidenceBar } from "@/components/ui/confidence-bar"
import {
  useTheories,
  useTasks,
  useWitnesses,
  useNotes,
  usePinnedItems,
} from "../hooks/use-workspace"
import { CalendarClock } from "lucide-react"
import { DeadlinesSection } from "@/features/cases/components/DeadlinesSection"
import { CaseContextSection } from "./CaseContextSection"
import { InvestigativeNotesSection } from "./InvestigativeNotesSection"
import { DocumentsSection } from "./DocumentsSection"
import { CaseFilesSection } from "./CaseFilesSection"

interface WorkspaceOverviewProps {
  caseId: string
}

function SummaryCard({
  icon: Icon,
  iconColor,
  title,
  count,
  children,
  className,
}: {
  icon: React.ComponentType<{ className?: string }>
  iconColor: string
  title: string
  count: number
  children: React.ReactNode
  className?: string
}) {
  return (
    <div className={`rounded-lg border border-border p-4 ${className ?? ""}`}>
      <div className="mb-3 flex items-center gap-2">
        <Icon className={`size-4 ${iconColor}`} />
        <h3 className="text-xs font-semibold">{title}</h3>
        <Badge variant="slate" className="h-4 px-1.5 text-[10px]">
          {count}
        </Badge>
      </div>
      {children}
    </div>
  )
}

const TYPE_COLORS: Record<string, string> = {
  PRIMARY: "text-blue-500",
  SECONDARY: "text-amber-500",
  NOTE: "text-muted-foreground",
}

export function WorkspaceOverview({ caseId }: WorkspaceOverviewProps) {
  const { data: theories = [] } = useTheories(caseId)
  const { data: tasks = [] } = useTasks(caseId)
  const { data: witnesses = [] } = useWitnesses(caseId)
  const { data: notes = [] } = useNotes(caseId)

  const completedTasks = tasks.filter(
    (t) => t.status?.toUpperCase() === "COMPLETED",
  ).length
  const pendingTasks = tasks.length - completedTasks

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-4">
      {/* Case Context — full width */}
      <CaseContextSection caseId={caseId} />

      {/* Deadlines — high priority, right under context */}
      <div className="rounded-lg border border-border p-4">
        <div className="mb-2 flex items-center gap-2">
          <CalendarClock className="size-4 text-red-500" />
          <h3 className="text-xs font-semibold">Deadlines</h3>
        </div>
        <DeadlinesSection caseId={caseId} />
      </div>

      {/* Summary cards grid */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        {/* Theories — spans 2 cols on large */}
        <SummaryCard
          icon={Lightbulb}
          iconColor="text-amber-500"
          title="Theories"
          count={theories.length}
          className="lg:col-span-2"
        >
          {theories.length === 0 ? (
            <p className="text-xs text-muted-foreground">No theories yet</p>
          ) : (
            <div className="space-y-2">
              {theories.slice(0, 3).map((t) => (
                <div key={t.id} className="flex items-center gap-2">
                  <Badge
                    variant="outline"
                    className={`shrink-0 text-[9px] ${TYPE_COLORS[t.type ?? "NOTE"] ?? ""}`}
                  >
                    {t.type ?? "NOTE"}
                  </Badge>
                  <span className="flex-1 truncate text-xs">{t.title}</span>
                  {t.confidence_score != null && (
                    <ConfidenceBar
                      value={t.confidence_score / 100}
                      className="w-20"
                      showLabel={false}
                    />
                  )}
                </div>
              ))}
              {theories.length > 3 && (
                <p className="text-[10px] text-muted-foreground">
                  +{theories.length - 3} more
                </p>
              )}
            </div>
          )}
        </SummaryCard>

        {/* Tasks */}
        <SummaryCard
          icon={CheckSquare}
          iconColor="text-blue-500"
          title="Tasks"
          count={tasks.length}
        >
          {tasks.length === 0 ? (
            <p className="text-xs text-muted-foreground">No tasks yet</p>
          ) : (
            <div className="space-y-2">
              {/* Progress bar */}
              <div className="space-y-1">
                <div className="flex justify-between text-[10px] text-muted-foreground">
                  <span>{completedTasks} completed</span>
                  <span>{pendingTasks} remaining</span>
                </div>
                <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full rounded-full bg-blue-500 transition-all"
                    style={{
                      width: `${tasks.length > 0 ? (completedTasks / tasks.length) * 100 : 0}%`,
                    }}
                  />
                </div>
              </div>
              {/* Recent tasks */}
              {tasks
                .filter((t) => t.status?.toUpperCase() !== "COMPLETED")
                .slice(0, 3)
                .map((t) => (
                  <div key={t.id} className="flex items-center gap-2">
                    <div className="size-1.5 shrink-0 rounded-full bg-muted-foreground/30" />
                    <span className="flex-1 truncate text-xs">{t.title}</span>
                    {t.priority && t.priority !== "STANDARD" && (
                      <Badge
                        variant="outline"
                        className={`text-[9px] ${
                          t.priority === "URGENT"
                            ? "text-red-500"
                            : "text-amber-500"
                        }`}
                      >
                        {t.priority}
                      </Badge>
                    )}
                  </div>
                ))}
            </div>
          )}
        </SummaryCard>

        {/* Witnesses */}
        <SummaryCard
          icon={Users}
          iconColor="text-violet-500"
          title="Witnesses"
          count={witnesses.length}
        >
          {witnesses.length === 0 ? (
            <p className="text-xs text-muted-foreground">No witnesses added</p>
          ) : (
            <div className="space-y-1.5">
              {witnesses.slice(0, 4).map((w) => (
                <div key={w.id} className="flex items-center gap-2">
                  <span className="flex-1 truncate text-xs">{w.name}</span>
                  {w.category && (
                    <Badge variant="outline" className="text-[9px]">
                      {w.category}
                    </Badge>
                  )}
                </div>
              ))}
              {witnesses.length > 4 && (
                <p className="text-[10px] text-muted-foreground">
                  +{witnesses.length - 4} more
                </p>
              )}
            </div>
          )}
        </SummaryCard>

        {/* Notes — full width on md */}
        <SummaryCard
          icon={StickyNote}
          iconColor="text-yellow-500"
          title="Notes"
          count={notes.length}
          className="md:col-span-2 lg:col-span-1"
        >
          {notes.length === 0 ? (
            <p className="text-xs text-muted-foreground">No notes yet</p>
          ) : (
            <div className="space-y-1.5">
              {notes.slice(0, 3).map((n) => (
                <div key={n.id}>
                  <p className="truncate text-xs font-medium">
                    {n.title || n.content.slice(0, 50)}
                  </p>
                  {n.tags && n.tags.length > 0 && (
                    <div className="mt-0.5 flex gap-1">
                      {n.tags.slice(0, 3).map((tag) => (
                        <Badge key={tag} variant="outline" className="text-[8px]">
                          {tag}
                        </Badge>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </SummaryCard>
      </div>

      {/* Secondary sections */}
      <div className="space-y-4 border-t border-border pt-4">
        <InvestigativeNotesSection caseId={caseId} />
        <DocumentsSection caseId={caseId} />
        <CaseFilesSection caseId={caseId} />
      </div>
    </div>
  )
}
