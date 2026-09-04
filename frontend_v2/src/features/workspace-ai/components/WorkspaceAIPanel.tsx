import { useMemo, useState } from "react"
import { DocumentViewer } from "@/components/ui/document-viewer"
import { evidenceAPI } from "@/features/evidence/api"
import {
  AlertTriangle,
  Ban,
  Check,
  ChevronDown,
  ChevronUp,
  FileSearch,
  Loader2,
  RefreshCcw,
  Sparkles,
  X,
} from "lucide-react"
import { toast } from "sonner"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Progress } from "@/components/ui/progress"
import { cn } from "@/lib/cn"
import type { DossierInterview } from "@/features/dossiers/api"
import {
  workspaceAIAPI,
  type WorkspaceAIClaim,
  type WorkspaceAICitation,
  type WorkspaceAIOutput,
  type WorkspaceAIOutputType,
  type WorkspaceAITargetType,
} from "../api"
import { useWorkspaceAIMutation, useWorkspaceAIOutputs } from "../hooks"

const GROUPS: Array<{
  key:
    | "claims"
    | "consistencies"
    | "contradictions"
    | "omissions"
    | "material_changes"
    | "supporting"
    | "contradicting"
  label: string
}> = [
  { key: "claims", label: "Cited statement summary" },
  { key: "consistencies", label: "Consistencies" },
  { key: "contradictions", label: "Contradictions" },
  { key: "omissions", label: "Omissions" },
  { key: "material_changes", label: "Material changes" },
  { key: "supporting", label: "Supporting material" },
  { key: "contradicting", label: "Contradicting material" },
]

function label(value: string) {
  return value
    .replaceAll("_", " ")
    .replace(/^./, (letter) => letter.toUpperCase())
}

function dateLabel(value?: string | null) {
  return value
    ? new Intl.DateTimeFormat(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(new Date(value))
    : "Not started"
}

function reviewVariant(output: WorkspaceAIOutput) {
  if (output.review_status === "rejected") return "danger" as const
  return "warning" as const
}

function CitationLinks({
  claim,
  output,
  onOpen,
}: {
  claim: WorkspaceAIClaim
  output: WorkspaceAIOutput
  onOpen: (citation: WorkspaceAICitation) => void
}) {
  const lookup = useMemo(
    () => new Map(output.citations.map((item) => [item.source_id, item])),
    [output.citations]
  )
  return (
    <span className="ml-1 inline-flex flex-wrap gap-1 align-middle">
      {claim.citation_ids.map((sourceId) => {
        const citation = lookup.get(sourceId)
        if (!citation) return null
        return (
          <button
            type="button"
            key={sourceId}
            onClick={() => onOpen(citation)}
            title={`${citation.filename}: ${citation.excerpt}`}
            className="cursor-pointer break-all text-left text-amber-500 underline underline-offset-2 hover:text-amber-400"
          >
            {citation.filename}
            {typeof citation.source_anchor.page === "number"
              ? `, p.${citation.source_anchor.page}`
              : ""}
            {typeof citation.source_anchor.start_seconds === "number"
              ? `, ${Math.floor(citation.source_anchor.start_seconds / 60)}:${String(Math.floor(citation.source_anchor.start_seconds % 60)).padStart(2, "0")}`
              : ""}
          </button>
        )
      })}
    </span>
  )
}

function OutputContent({ output }: { output: WorkspaceAIOutput }) {
  const [source, setSource] = useState<WorkspaceAICitation | null>(null)
  return (
    <div className="space-y-4">
      {GROUPS.map(({ key, label: groupLabel }) => {
        const claims = output.content[key]
        const notFound =
          output.content[
            `${key}_not_found_reason` as keyof typeof output.content
          ]
        if (!claims?.length && !notFound) return null
        return (
          <section key={key}>
            <h5 className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
              {groupLabel}
            </h5>
            {claims?.length ? (
              <ul className="mt-1.5 space-y-2">
                {claims.map((claim, index) => (
                  <li key={`${key}-${index}`} className="text-xs leading-5">
                    {claim.text}
                    <CitationLinks
                      claim={claim}
                      output={output}
                      onOpen={setSource}
                    />
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-1.5 rounded-md bg-muted/40 p-2 text-xs text-muted-foreground">
                No material found: {String(notFound)}
              </p>
            )}
          </section>
        )
      })}
      <DocumentViewer
        open={source !== null}
        onOpenChange={(open) => {
          if (!open) setSource(null)
        }}
        documentUrl={
          source ? evidenceAPI.getFileUrl(source.evidence_file_id) : undefined
        }
        documentName={source?.filename}
        initialPage={
          typeof source?.source_anchor.page === "number"
            ? source.source_anchor.page
            : undefined
        }
        initialTime={
          typeof source?.source_anchor.start_seconds === "number"
            ? source.source_anchor.start_seconds
            : undefined
        }
      />
      {output.content.limitations?.length ? (
        <section>
          <h5 className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            Limitations
          </h5>
          <ul className="mt-1.5 list-disc space-y-1 pl-4 text-xs text-muted-foreground">
            {output.content.limitations.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  )
}

function OutputCard({
  caseId,
  targetType,
  targetId,
  output,
  canEdit,
}: {
  caseId: string
  targetType: WorkspaceAITargetType
  targetId: string
  output: WorkspaceAIOutput
  canEdit: boolean
}) {
  const [expanded, setExpanded] = useState(false)
  const [rejectionReason, setRejectionReason] = useState("")
  const cancel = useWorkspaceAIMutation(caseId, targetType, targetId, () =>
    workspaceAIAPI.cancel(caseId, output.id)
  )
  const retry = useWorkspaceAIMutation(caseId, targetType, targetId, () =>
    workspaceAIAPI.retry(caseId, output.id)
  )
  const accept = useWorkspaceAIMutation(caseId, targetType, targetId, () =>
    workspaceAIAPI.accept(caseId, output.id)
  )
  const reject = useWorkspaceAIMutation(caseId, targetType, targetId, () =>
    workspaceAIAPI.reject(caseId, output.id, rejectionReason)
  )
  const act = async (
    action: "cancel" | "retry" | "accept" | "reject",
    run: () => Promise<unknown>
  ) => {
    try {
      await run()
      toast.success(
        action === "accept"
          ? "AI proposal accepted into casework"
          : action === "reject"
            ? "AI proposal rejected and retained"
            : action === "retry"
              ? "New output version started"
              : "Cancellation requested"
      )
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : `Could not ${action} output`
      )
    }
  }
  const active = ["queued", "running"].includes(output.job_status)
  const pendingReview =
    output.job_status === "completed" &&
    output.review_status === "pending_review"
  return (
    <article
      className={cn(
        "overflow-hidden rounded-lg border border-border bg-card",
        output.review_status === "rejected" &&
          "border-red-200 opacity-80 dark:border-red-950"
      )}
    >
      <button
        type="button"
        className="flex w-full items-start gap-3 p-3 text-left"
        onClick={() => setExpanded((value) => !value)}
        aria-expanded={expanded}
      >
        {active ? (
          <Loader2 className="mt-0.5 size-4 shrink-0 animate-spin text-brand-600" />
        ) : output.job_status === "failed" ? (
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-red-500" />
        ) : output.job_status === "cancelled" ? (
          <Ban className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
        ) : (
          <FileSearch className="mt-0.5 size-4 shrink-0 text-brand-600" />
        )}
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-1.5">
            <span className="text-xs font-semibold">
              {output.content.headline || label(output.output_type)}
            </span>
            <Badge variant="outline">v{output.version}</Badge>
            {output.job_status === "completed" &&
            output.review_status !== "accepted" ? (
              <Badge variant={reviewVariant(output)}>
                {label(output.review_status)}
              </Badge>
            ) : output.job_status !== "completed" ? (
              <Badge
                variant={output.job_status === "failed" ? "danger" : "slate"}
              >
                {label(output.job_status)}
              </Badge>
            ) : null}
          </span>
          <span className="mt-1 block text-[10px] text-muted-foreground">
            Mandate v{output.mandate_version_number ?? "?"} · requested by{" "}
            {output.requested_by_name || "an investigator"} ·{" "}
            {dateLabel(output.created_at)}
            {output.review_status === "accepted"
              ? ` - Accepted by ${output.reviewed_by_name || "an investigator"}`
              : ""}
          </span>
        </span>
        {expanded ? (
          <ChevronUp className="size-4" />
        ) : (
          <ChevronDown className="size-4" />
        )}
      </button>
      {active ? (
        <div className="px-3 pb-3">
          <Progress value={output.progress} className="h-1.5" />
          <div className="mt-2 flex items-center justify-between text-[10px] text-muted-foreground">
            <span>
              {output.cancel_requested
                ? "Cancellation requested"
                : "Safe to leave this page; progress is stored."}
            </span>
            {canEdit && !output.cancel_requested ? (
              <Button
                variant="ghost"
                size="sm"
                className="h-6 px-2 text-[10px]"
                onClick={() => void act("cancel", () => cancel.mutateAsync())}
              >
                Cancel
              </Button>
            ) : null}
          </div>
        </div>
      ) : null}
      {expanded && !active ? (
        <div className="space-y-4 border-t border-border p-3">
          {output.job_status === "completed" ? (
            <OutputContent output={output} />
          ) : null}
          {output.error_message ? (
            <p className="rounded-md bg-red-50 p-2 text-xs text-red-700 dark:bg-red-950/30 dark:text-red-300">
              {output.error_message}
            </p>
          ) : null}
          {output.rejection_reason ? (
            <p className="rounded-md bg-muted/40 p-2 text-xs text-muted-foreground">
              Rejection note: {output.rejection_reason}
            </p>
          ) : null}
          {canEdit && pendingReview ? (
            <div className="space-y-2 border-t border-border pt-3">
              <p className="text-[11px] text-muted-foreground">
                Review the cited proposal. Nothing changes in casework until you
                accept it.
              </p>
              <input
                value={rejectionReason}
                onChange={(event) => setRejectionReason(event.target.value)}
                className="h-8 w-full rounded-md border border-input bg-background px-2.5 text-xs"
                placeholder="Optional rejection note"
                aria-label="Rejection note"
              />
              <div className="flex flex-wrap gap-2">
                <Button
                  size="sm"
                  onClick={() => void act("accept", () => accept.mutateAsync())}
                  disabled={accept.isPending}
                >
                  {accept.isPending ? (
                    <Loader2 className="size-3.5 animate-spin" />
                  ) : (
                    <Check className="size-3.5" />
                  )}{" "}
                  Accept proposal
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => void act("reject", () => reject.mutateAsync())}
                  disabled={reject.isPending}
                >
                  <X className="size-3.5" /> Reject
                </Button>
              </div>
            </div>
          ) : null}
          {canEdit &&
          ["completed", "failed", "cancelled"].includes(output.job_status) ? (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => void act("retry", () => retry.mutateAsync())}
              disabled={retry.isPending}
            >
              {retry.isPending ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <RefreshCcw className="size-3.5" />
              )}{" "}
              Regenerate as a new version
            </Button>
          ) : null}
        </div>
      ) : null}
    </article>
  )
}

function outputGroups(outputs: WorkspaceAIOutput[]) {
  const byId = new Map(outputs.map((output) => [output.id, output]))
  const groups = new Map<string, WorkspaceAIOutput[]>()
  for (const output of outputs) {
    let root = output
    const visited = new Set<string>()
    while (root.parent_output_id && byId.has(root.parent_output_id) && !visited.has(root.id)) {
      visited.add(root.id)
      root = byId.get(root.parent_output_id)!
    }
    const interviews = [...new Set(root.source_set.map((source) => source.interview_id).filter(Boolean))].sort()
    const key = `${output.output_type}:${interviews.length ? interviews.join(",") : root.id}`
    const group = groups.get(key) ?? []
    group.push(output)
    groups.set(key, group)
  }
  return [...groups.entries()].map(([key, versions]) => ({
    key,
    versions: versions.sort((a, b) => b.version - a.version),
  }))
}

function OutputVersions({ versions, ...props }: {
  versions: WorkspaceAIOutput[]
  caseId: string
  targetType: WorkspaceAITargetType
  targetId: string
  canEdit: boolean
}) {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const output = versions.find((item) => item.id === selectedId) ?? versions[0]
  return (
    <div className="space-y-1.5">
      {versions.length > 1 ? (
        <div className="flex justify-end">
          <select
            aria-label="Summary version"
            className="max-w-full rounded border border-border bg-background px-2 py-1 text-xs text-muted-foreground"
            value={output.id}
            onChange={(event) => setSelectedId(event.target.value === versions[0].id ? null : event.target.value)}
          >
            {versions.map((version, index) => (
              <option key={version.id} value={version.id}>
                {index === 0 ? "Latest · " : ""}Version {version.version} · {dateLabel(version.created_at)}
              </option>
            ))}
          </select>
        </div>
      ) : null}
      <OutputCard key={output.id} {...props} output={output} />
    </div>
  )
}

export function WorkspaceAIPanel({
  caseId,
  targetType,
  targetId,
  canEdit,
  interviews = [],
}: {
  caseId: string
  targetType: WorkspaceAITargetType
  targetId: string
  canEdit: boolean
  interviews?: DossierInterview[]
}) {
  const outputs = useWorkspaceAIOutputs(caseId, targetType, targetId)
  const [selectedInterviews, setSelectedInterviews] = useState<string[]>([])
  const [startingType, setStartingType] =
    useState<WorkspaceAIOutputType | null>(null)
  const startOutput = async (outputType: WorkspaceAIOutputType) => {
    setStartingType(outputType)
    try {
      await workspaceAIAPI.start(caseId, {
        target_type: targetType,
        target_id: targetId,
        output_type: outputType,
        interview_ids: selectedInterviews,
      })
      await outputs.refetch()
      toast.success("Workspace AI job started")
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Could not start Workspace AI"
      )
    } finally {
      setStartingType(null)
    }
  }
  const toggleInterview = (interviewId: string) => {
    setSelectedInterviews((current) =>
      current.includes(interviewId)
        ? current.filter((id) => id !== interviewId)
        : [...current, interviewId]
    )
  }
  return (
    <section className="space-y-3">
      <div className="flex items-start gap-3">
        <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-brand-500/10">
          <Sparkles className="size-4 text-brand-600" />
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-semibold">Cited AI assistance</h3>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Generated analysis remains separate from casework until an
            investigator reviews and accepts it.
          </p>
        </div>
      </div>

      {canEdit && targetType === "dossier" ? (
        <div className="space-y-2 rounded-lg border border-border bg-background p-3">
          <p className="text-xs font-semibold">
            Select linked interviews or statements
          </p>
          {interviews.length ? (
            <div className="space-y-1.5">
              {interviews.map((interview, index) => (
                <label
                  key={interview.id}
                  className="flex cursor-pointer items-start gap-2 rounded-md p-1.5 hover:bg-muted/40"
                >
                  <Checkbox
                    checked={selectedInterviews.includes(interview.id)}
                    onCheckedChange={() => toggleInterview(interview.id)}
                    aria-label={`Select interview ${index + 1}`}
                  />
                  <span className="text-xs">
                    Interview {index + 1} ·{" "}
                    {dateLabel(interview.interview_date)} ·{" "}
                    {interview.evidence_links.length} source
                    {interview.evidence_links.length === 1 ? "" : "s"}
                  </span>
                </label>
              ))}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">
              Add an interview with linked textual or audio evidence first.
            </p>
          )}
          <div className="flex flex-wrap gap-2 pt-1">
            <Button
              size="sm"
              variant="outline"
              disabled={selectedInterviews.length < 1 || startingType !== null}
              onClick={() => void startOutput("statement_summary")}
            >
              {startingType === "statement_summary" ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <FileSearch className="size-3.5" />
              )}{" "}
              Summarise selection
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={selectedInterviews.length < 2 || startingType !== null}
              onClick={() => void startOutput("statement_comparison")}
            >
              {startingType === "statement_comparison" ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <FileSearch className="size-3.5" />
              )}{" "}
              Compare statements
            </Button>
          </div>
        </div>
      ) : null}

      {canEdit && targetType === "theory" ? (
        <Button
          size="sm"
          variant="outline"
          disabled={startingType !== null}
          onClick={() => void startOutput("theory_analysis")}
        >
          {startingType === "theory_analysis" ? (
            <Loader2 className="size-3.5 animate-spin" />
          ) : (
            <Sparkles className="size-3.5" />
          )}{" "}
          Search both sides of this Theory
        </Button>
      ) : null}

      {outputs.isLoading ? (
        <div className="flex items-center gap-2 py-3 text-xs text-muted-foreground">
          <Loader2 className="size-3.5 animate-spin" /> Loading generated work
        </div>
      ) : outputs.isError ? (
        <p className="rounded-md bg-red-50 p-2 text-xs text-red-700 dark:bg-red-950/30 dark:text-red-300">
          Generated work could not be loaded.
        </p>
      ) : outputs.data?.outputs.length ? (
        <div className="space-y-2">
          {outputGroups(outputs.data.outputs).map(({ key, versions }) => (
            <OutputVersions
              key={key}
              caseId={caseId}
              targetType={targetType}
              targetId={targetId}
              versions={versions}
              canEdit={canEdit}
            />
          ))}
        </div>
      ) : (
        <p className="rounded-lg border border-dashed border-border bg-background/60 py-6 text-center text-xs text-muted-foreground">
          No generated analysis yet.
        </p>
      )}
    </section>
  )
}
