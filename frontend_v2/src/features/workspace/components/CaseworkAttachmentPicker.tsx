import { useMemo, useState } from "react"
import {
  Bot,
  CalendarClock,
  CheckSquare,
  FileSearch,
  GitBranch,
  History,
  ContactRound,
  Link2,
  Loader2,
  Plus,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/cn"
import { NotebookEntityPicker } from "@/features/notebook/components/NotebookEntityPicker"
import type {
  CaseworkLinkInput,
  CaseworkLinkTargetType,
} from "../casework-api"
import { useAttachmentOptions } from "../hooks/use-casework"

interface CaseworkAttachmentPickerProps {
  caseId: string
  onAttach: (link: CaseworkLinkInput) => void
}

const TARGETS: Array<{
  value: CaseworkLinkTargetType
  label: string
  icon: typeof Link2
}> = [
  { value: "evidence", label: "Evidence", icon: FileSearch },
  { value: "graph_entity", label: "Entity", icon: GitBranch },
  { value: "dossier", label: "Dossier", icon: ContactRound },
  { value: "entry", label: "Casework", icon: Link2 },
  { value: "task", label: "Task", icon: CheckSquare },
  { value: "deadline", label: "Deadline", icon: CalendarClock },
  { value: "timeline_event", label: "Event", icon: History },
  { value: "agent_artifact", label: "AI output", icon: Bot },
]

export function CaseworkAttachmentPicker({
  caseId,
  onAttach,
}: CaseworkAttachmentPickerProps) {
  const [targetType, setTargetType] = useState<CaseworkLinkTargetType>("evidence")
  const [query, setQuery] = useState("")
  const optionsQuery = useAttachmentOptions(
    caseId,
    targetType,
    query.trim(),
    targetType !== "graph_entity",
  )
  const activeTarget = useMemo(
    () => TARGETS.find((item) => item.value === targetType) ?? TARGETS[0],
    [targetType],
  )

  return (
    <div className="overflow-hidden rounded-lg border border-border bg-background">
      <div className="flex gap-1 overflow-x-auto border-b border-border bg-muted/25 p-1.5">
        {TARGETS.map((target) => {
          const Icon = target.icon
          return (
            <button
              key={target.value}
              type="button"
              onClick={() => {
                setTargetType(target.value)
                setQuery("")
              }}
              className={cn(
                "inline-flex h-7 shrink-0 items-center gap-1.5 rounded-md px-2 text-[11px] font-medium text-muted-foreground transition-colors",
                targetType === target.value
                  ? "bg-background text-foreground shadow-sm ring-1 ring-border"
                  : "hover:bg-background/60 hover:text-foreground",
              )}
            >
              <Icon className="size-3" />
              {target.label}
            </button>
          )
        })}
      </div>

      {targetType === "graph_entity" ? (
        <div className="p-2.5">
          <NotebookEntityPicker
            caseId={caseId}
            onAttach={(link) =>
              onAttach({
                target_type: "graph_entity",
                target_id: link.target_id,
                target_label: link.target_label,
                relationship: "unclassified",
                metadata: link.metadata,
              })
            }
          />
        </div>
      ) : (
        <div>
          <div className="border-b border-border p-2.5">
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={`Search ${activeTarget.label.toLowerCase()}…`}
              aria-label={`Search ${activeTarget.label}`}
              className="h-8 bg-card text-xs"
            />
          </div>
          <div className="max-h-48 overflow-y-auto p-1.5" aria-live="polite">
            {optionsQuery.isLoading ? (
              <div className="flex items-center justify-center gap-2 py-6 text-xs text-muted-foreground">
                <Loader2 className="size-3.5 animate-spin" />
                Searching
              </div>
            ) : optionsQuery.isError ? (
              <div className="p-3 text-xs text-muted-foreground" role="alert">
                Could not load {activeTarget.label.toLowerCase()}.
                <Button type="button" variant="ghost" size="sm" onClick={() => void optionsQuery.refetch()}>Retry</Button>
              </div>
            ) : optionsQuery.data?.items.length ? (
              optionsQuery.data.items.map((option) => (
                <div
                  key={`${option.target_type}:${option.target_id}`}
                  className="group flex items-start gap-2 rounded-md px-2.5 py-2 hover:bg-muted/50"
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-xs font-medium text-foreground">
                      {option.label}
                    </p>
                    {option.description && (
                      <p className="mt-0.5 line-clamp-2 text-[11px] leading-relaxed text-muted-foreground">
                        {option.description}
                      </p>
                    )}
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="h-7 shrink-0 px-2 text-[11px]"
                    onClick={() =>
                      onAttach({
                        target_type: option.target_type,
                        target_id: option.target_id,
                        target_label: option.label,
                        relationship: "unclassified",
                        metadata: option.metadata,
                      })
                    }
                  >
                    <Plus className="size-3" />
                    Attach
                  </Button>
                </div>
              ))
            ) : (
              <p className="px-3 py-6 text-center text-xs text-muted-foreground">
                No matching {activeTarget.label.toLowerCase()} in this case.
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
