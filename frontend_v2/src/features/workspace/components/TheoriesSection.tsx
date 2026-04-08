import { useState } from "react"
import {
  Lightbulb,
  Plus,
  Lock,
  Shield,
  FileText,
  Users,
  StickyNote,
  CheckSquare,
  File,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { ConfidenceBar } from "@/components/ui/confidence-bar"
import { useTheories } from "../hooks/use-workspace"
import type { Theory } from "../api"
import { CreateTheoryDialog } from "./CreateTheoryDialog"
import { TheoryDetailSheet } from "./TheoryDetailSheet"
import { formatWorkspaceDate } from "../lib/format-date"

interface TheoriesSectionProps {
  caseId: string
}

const TYPE_STYLE: Record<string, { label: string; variant: "default" | "outline" | "slate" }> = {
  PRIMARY: { label: "Primary", variant: "default" },
  SECONDARY: { label: "Secondary", variant: "outline" },
  NOTE: { label: "Note", variant: "slate" },
}

function AttachedCount({ icon: Icon, count }: { icon: React.ComponentType<{ className?: string }>; count: number }) {
  if (count === 0) return null
  return (
    <span className="flex items-center gap-0.5 text-[10px] text-muted-foreground">
      <Icon className="size-2.5" />
      {count}
    </span>
  )
}

export function TheoriesSection({ caseId }: TheoriesSectionProps) {
  const { data: theories = [], isLoading } = useTheories(caseId)
  const [createOpen, setCreateOpen] = useState(false)
  const [selectedTheoryId, setSelectedTheoryId] = useState<string | null>(null)
  const [detailOpen, setDetailOpen] = useState(false)

  const selectedTheory = selectedTheoryId
    ? theories.find((t) => t.id === selectedTheoryId) ?? null
    : null

  const openDetail = (theory: Theory) => {
    setSelectedTheoryId(theory.id)
    setDetailOpen(true)
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Lightbulb className="size-4 text-amber-500" />
          <h2 className="text-sm font-semibold">Theories</h2>
          <Badge variant="slate" className="h-5 px-1.5 text-[10px]">
            {theories.length}
          </Badge>
        </div>
        <Button variant="outline" size="sm" onClick={() => setCreateOpen(true)}>
          <Plus className="mr-1 size-3" />
          New Theory
        </Button>
      </div>

      {/* Theory cards */}
      {isLoading ? (
        <div className="space-y-3">
          {[1, 2].map((i) => (
            <div key={i} className="h-24 animate-pulse rounded-lg border border-border bg-muted/30" />
          ))}
        </div>
      ) : theories.length === 0 ? (
        <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-border py-10">
          <Lightbulb className="size-8 text-muted-foreground/40" />
          <p className="text-xs text-muted-foreground">No theories yet</p>
          <Button variant="outline" size="sm" onClick={() => setCreateOpen(true)}>
            <Plus className="mr-1 size-3" />
            Create your first theory
          </Button>
        </div>
      ) : (
        <div className="space-y-3">
          {theories.map((theory) => {
            const typeStyle = TYPE_STYLE[theory.type ?? "NOTE"] ?? TYPE_STYLE.NOTE
            const isPrivate = theory.privilege_level === "ATTORNEY_ONLY" || theory.privilege_level === "PRIVATE"
            const evidenceCount = theory.attached_evidence_ids?.length ?? 0
            const witnessCount = theory.attached_witness_ids?.length ?? 0
            const noteCount = theory.attached_note_ids?.length ?? 0
            const taskCount = theory.attached_task_ids?.length ?? 0
            const docCount = theory.attached_document_ids?.length ?? 0
            const hasAttachments = evidenceCount + witnessCount + noteCount + taskCount + docCount > 0

            return (
              <button
                key={theory.id}
                onClick={() => openDetail(theory)}
                className="w-full rounded-lg border border-border p-3 text-left transition-colors hover:bg-muted/30"
              >
                {/* Top row: type + title + privilege */}
                <div className="flex items-start gap-2">
                  <Badge variant={typeStyle.variant} className="mt-0.5 shrink-0 text-[10px]">
                    {typeStyle.label}
                  </Badge>
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-medium leading-snug">{theory.title}</p>
                  </div>
                  {isPrivate && (
                    <span className="shrink-0 text-muted-foreground">
                      {theory.privilege_level === "ATTORNEY_ONLY" ? (
                        <Shield className="size-3.5" />
                      ) : (
                        <Lock className="size-3.5" />
                      )}
                    </span>
                  )}
                </div>

                {/* Hypothesis preview */}
                {theory.hypothesis && (
                  <p className="mt-1.5 line-clamp-2 text-[11px] leading-relaxed text-muted-foreground">
                    {theory.hypothesis}
                  </p>
                )}

                {/* Confidence bar */}
                {theory.confidence_score != null && (
                  <div className="mt-2">
                    <ConfidenceBar value={theory.confidence_score / 100} className="max-w-48" />
                  </div>
                )}

                {/* Attached items */}
                {hasAttachments && (
                  <div className="mt-2 flex gap-3">
                    <AttachedCount icon={FileText} count={evidenceCount} />
                    <AttachedCount icon={Users} count={witnessCount} />
                    <AttachedCount icon={StickyNote} count={noteCount} />
                    <AttachedCount icon={CheckSquare} count={taskCount} />
                    <AttachedCount icon={File} count={docCount} />
                  </div>
                )}

                {/* Footer */}
                {(theory.author_id || theory.created_at) && (
                  <div className="mt-2 flex items-center gap-2 text-[10px] text-muted-foreground/60">
                    {theory.author_id && <span>{theory.author_id}</span>}
                    {theory.created_at && (
                      <span>{formatWorkspaceDate(theory.created_at)}</span>
                    )}
                  </div>
                )}
              </button>
            )
          })}
        </div>
      )}

      {/* Dialogs */}
      <CreateTheoryDialog open={createOpen} onOpenChange={setCreateOpen} caseId={caseId} />
      <TheoryDetailSheet
        theory={selectedTheory}
        open={detailOpen}
        onOpenChange={setDetailOpen}
        caseId={caseId}
      />
    </div>
  )
}
