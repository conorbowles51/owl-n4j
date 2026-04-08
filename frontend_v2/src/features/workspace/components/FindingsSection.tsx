import { useMemo, useState } from "react"
import { AlertCircle, Plus, Trash2, Link2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import {
  useCreateFinding,
  useDeleteFinding,
  useFindings,
  useUpdateFinding,
} from "../hooks/use-workspace"
import type { Finding } from "../api"
import { formatWorkspaceDate } from "../lib/format-date"

interface FindingsSectionProps {
  caseId: string
  previewLimit?: number
}

const PRIORITY_STYLES: Record<string, string> = {
  HIGH: "bg-red-500/10 text-red-600 border-red-500/20",
  MEDIUM: "bg-amber-500/10 text-amber-600 border-amber-500/20",
  LOW: "bg-slate-500/10 text-slate-600 border-slate-500/20",
}

function countLinkedItems(finding: Finding) {
  return (
    (finding.linked_evidence_ids?.length ?? 0) +
    (finding.linked_document_ids?.length ?? 0) +
    (finding.linked_entity_keys?.length ?? 0)
  )
}

export function FindingsSection({ caseId, previewLimit }: FindingsSectionProps) {
  const { data: findings = [], isLoading } = useFindings(caseId)
  const createFinding = useCreateFinding(caseId)
  const updateFinding = useUpdateFinding(caseId)
  const deleteFinding = useDeleteFinding(caseId)

  const [editorOpen, setEditorOpen] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [title, setTitle] = useState("")
  const [content, setContent] = useState("")
  const [priority, setPriority] = useState<Finding["priority"]>("MEDIUM")
  const [linkedEvidence, setLinkedEvidence] = useState("")
  const [linkedDocuments, setLinkedDocuments] = useState("")
  const [linkedEntities, setLinkedEntities] = useState("")

  const visibleFindings = useMemo(
    () => (previewLimit ? findings.slice(0, previewLimit) : findings),
    [findings, previewLimit],
  )

  const resetEditor = () => {
    setEditorOpen(false)
    setEditingId(null)
    setTitle("")
    setContent("")
    setPriority("MEDIUM")
    setLinkedEvidence("")
    setLinkedDocuments("")
    setLinkedEntities("")
  }

  const openEditor = (finding?: Finding) => {
    if (finding) {
      setEditingId(finding.id)
      setTitle(finding.title)
      setContent(finding.content ?? "")
      setPriority(finding.priority ?? "MEDIUM")
      setLinkedEvidence((finding.linked_evidence_ids ?? []).join(", "))
      setLinkedDocuments((finding.linked_document_ids ?? []).join(", "))
      setLinkedEntities((finding.linked_entity_keys ?? []).join(", "))
    } else {
      resetEditor()
      setEditorOpen(true)
      return
    }
    setEditorOpen(true)
  }

  const toList = (value: string) =>
    value
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean)

  const handleSave = () => {
    const payload = {
      title: title.trim(),
      content: content.trim() || undefined,
      priority,
      linked_evidence_ids: toList(linkedEvidence),
      linked_document_ids: toList(linkedDocuments),
      linked_entity_keys: toList(linkedEntities),
    }
    if (!payload.title) return

    if (editingId) {
      updateFinding.mutate(
        { findingId: editingId, updates: payload },
        { onSuccess: resetEditor },
      )
      return
    }

    createFinding.mutate(payload, { onSuccess: resetEditor })
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <AlertCircle className="size-4 text-rose-500" />
          <h2 className="text-sm font-semibold">Findings</h2>
          <Badge variant="slate" className="h-5 px-1.5 text-[10px]">
            {findings.length}
          </Badge>
        </div>
        {!previewLimit && (
          <Button variant="outline" size="sm" onClick={() => openEditor()}>
            <Plus className="mr-1 size-3" />
            New Finding
          </Button>
        )}
      </div>

      {editorOpen && !previewLimit && (
        <div className="space-y-3 rounded-lg border border-border p-4">
          <div className="grid gap-3 md:grid-cols-2">
            <Input
              placeholder="Finding title"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
            />
            <select
              value={priority}
              onChange={(event) => setPriority(event.target.value)}
              className="h-10 rounded-md border border-input bg-background px-3 text-sm"
            >
              <option value="HIGH">High</option>
              <option value="MEDIUM">Medium</option>
              <option value="LOW">Low</option>
            </select>
          </div>
          <Textarea
            rows={4}
            placeholder="What did you conclude, and why does it matter?"
            value={content}
            onChange={(event) => setContent(event.target.value)}
          />
          <div className="grid gap-3 md:grid-cols-3">
            <Input
              placeholder="Evidence IDs, comma separated"
              value={linkedEvidence}
              onChange={(event) => setLinkedEvidence(event.target.value)}
            />
            <Input
              placeholder="Document IDs, comma separated"
              value={linkedDocuments}
              onChange={(event) => setLinkedDocuments(event.target.value)}
            />
            <Input
              placeholder="Entity keys, comma separated"
              value={linkedEntities}
              onChange={(event) => setLinkedEntities(event.target.value)}
            />
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" size="sm" onClick={resetEditor}>
              Cancel
            </Button>
            <Button size="sm" onClick={handleSave} disabled={!title.trim()}>
              Save
            </Button>
          </div>
        </div>
      )}

      {isLoading ? (
        <div className="space-y-2">
          {[1, 2].map((index) => (
            <div key={index} className="h-20 animate-pulse rounded-lg bg-muted/30" />
          ))}
        </div>
      ) : visibleFindings.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border py-8 text-center text-xs text-muted-foreground">
          No findings yet.
        </div>
      ) : (
        <div className="space-y-3">
          {visibleFindings.map((finding) => {
            const priorityClass =
              PRIORITY_STYLES[(finding.priority ?? "MEDIUM").toUpperCase()] ??
              PRIORITY_STYLES.MEDIUM
            return (
              <div key={finding.id} className="rounded-lg border border-border p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-sm font-medium">{finding.title}</p>
                      <Badge variant="outline" className={`text-[10px] ${priorityClass}`}>
                        {finding.priority ?? "MEDIUM"}
                      </Badge>
                    </div>
                    {finding.content && (
                      <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
                        {finding.content}
                      </p>
                    )}
                    <div className="mt-2 flex flex-wrap items-center gap-2 text-[10px] text-muted-foreground">
                      {countLinkedItems(finding) > 0 && (
                        <span className="inline-flex items-center gap-1">
                          <Link2 className="size-3" />
                          {countLinkedItems(finding)} linked items
                        </span>
                      )}
                      {finding.updated_at && <span>{formatWorkspaceDate(finding.updated_at)}</span>}
                    </div>
                  </div>
                  {!previewLimit && (
                    <div className="flex items-center gap-1">
                      <Button variant="ghost" size="sm" onClick={() => openEditor(finding)}>
                        Edit
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        onClick={() => deleteFinding.mutate(finding.id)}
                      >
                        <Trash2 className="size-3.5" />
                      </Button>
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
