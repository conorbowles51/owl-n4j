import { useState, useEffect } from "react"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { NodeBadge } from "@/components/ui/node-badge"
import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"
import { Checkbox } from "@/components/ui/checkbox"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Textarea } from "@/components/ui/textarea"
import { markdownToPlainText } from "@/lib/markdown-text"
import type { GraphNode, VerifiedFact, AIInsight } from "@/types/graph.types"
import { graphAPI } from "../api"
import { GitMerge, AlertTriangle, Plus, Trash2, ArrowRightLeft } from "lucide-react"

/* ── Internal types ── */

type PickMode = "entityA" | "entityB" | "both"

interface SelectableItem<T> {
  data: T
  source: "entityA" | "entityB"
  selected: boolean
}

interface CustomField {
  name: string
  value: string
}

/* ── Props (unchanged) ── */

interface MergeEntitiesDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  entity1: GraphNode | null
  entity2: GraphNode | null
  caseId: string
  similarity?: number
  onMerged?: () => void
}

/* ── Inline helpers ── */

function PickModeToggle({
  value,
  onChange,
  labelA,
  labelB,
}: {
  value: PickMode
  onChange: (v: PickMode) => void
  labelA: string
  labelB: string
}) {
  const opts: { key: PickMode; label: string }[] = [
    { key: "entityA", label: truncate(labelA, 14) },
    { key: "entityB", label: truncate(labelB, 14) },
    { key: "both", label: "Both" },
  ]
  return (
    <div className="inline-flex rounded-md border border-border">
      {opts.map((o) => (
        <button
          key={o.key}
          type="button"
          className={`px-2.5 py-1 text-xs font-medium transition-colors first:rounded-l-md last:rounded-r-md ${
            value === o.key
              ? "bg-amber-500 text-white"
              : "bg-transparent text-muted-foreground hover:bg-muted"
          }`}
          onClick={() => onChange(o.key)}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

function EntityPreviewCard({
  entity,
  tag,
  borderClass,
}: {
  entity: GraphNode
  tag: string
  borderClass: string
}) {
  const summaryText = entity.summary ? markdownToPlainText(entity.summary) : null

  return (
    <div className={`rounded-lg border-2 p-3 ${borderClass}`}>
      <div className="mb-1.5 flex items-center gap-1.5">
        <NodeBadge type={entity.type} />
        <Badge variant="outline" className="text-[10px]">
          {tag}
        </Badge>
      </div>
      <p className="text-sm font-medium leading-tight">{entity.label}</p>
      {summaryText && (
        <p className="mt-1 line-clamp-3 text-xs text-muted-foreground">
          {summaryText}
        </p>
      )}
      <div className="mt-2 flex gap-3 text-[10px] text-muted-foreground">
        <span>{entity.verified_facts?.length ?? 0} facts</span>
        <span>{entity.ai_insights?.length ?? 0} insights</span>
      </div>
    </div>
  )
}

function SourceBadge({ source }: { source: "entityA" | "entityB" }) {
  return source === "entityA" ? (
    <Badge className="bg-blue-500/15 text-blue-700 dark:text-blue-400 text-[10px] px-1.5">
      A
    </Badge>
  ) : (
    <Badge className="bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 text-[10px] px-1.5">
      B
    </Badge>
  )
}

function truncate(s: string, max: number) {
  return s.length > max ? s.slice(0, max) + "…" : s
}

/* ── Main component ── */

export function MergeEntitiesDialog({
  open,
  onOpenChange,
  entity1,
  entity2,
  caseId,
  similarity,
  onMerged,
}: MergeEntitiesDialogProps) {
  const [keepEntity, setKeepEntity] = useState<1 | 2>(1)
  const [nameMode, setNameMode] = useState<PickMode>("both")
  const [summaryMode, setSummaryMode] = useState<PickMode>("both")
  const [mergedName, setMergedName] = useState("")
  const [mergedSummary, setMergedSummary] = useState("")
  const [mergedType, setMergedType] = useState("")
  const [facts, setFacts] = useState<SelectableItem<VerifiedFact>[]>([])
  const [insights, setInsights] = useState<SelectableItem<AIInsight>[]>([])
  const [customFields, setCustomFields] = useState<CustomField[]>([])
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Reset all state when dialog opens or entities change
  useEffect(() => {
    if (!open || !entity1 || !entity2) return
    setKeepEntity(1)
    setNameMode("both")
    setSummaryMode("both")
    setMergedName(`${entity1.label} / ${entity2.label}`)
    setMergedSummary(
      [entity1.summary, entity2.summary].filter(Boolean).join("\n\n---\n\n")
    )
    setMergedType(entity1.type)
    setFacts([
      ...(entity1.verified_facts ?? []).map((f) => ({
        data: f,
        source: "entityA" as const,
        selected: true,
      })),
      ...(entity2.verified_facts ?? []).map((f) => ({
        data: f,
        source: "entityB" as const,
        selected: true,
      })),
    ])
    setInsights([
      ...(entity1.ai_insights ?? []).map((i) => ({
        data: i,
        source: "entityA" as const,
        selected: true,
      })),
      ...(entity2.ai_insights ?? []).map((i) => ({
        data: i,
        source: "entityB" as const,
        selected: true,
      })),
    ])
    setCustomFields([])
    setSaving(false)
    setError(null)
  }, [open, entity1?.key, entity2?.key])

  // Sync merged name with pick mode
  useEffect(() => {
    if (!entity1 || !entity2) return
    if (nameMode === "entityA") setMergedName(entity1.label)
    else if (nameMode === "entityB") setMergedName(entity2.label)
    else setMergedName(`${entity1.label} / ${entity2.label}`)
  }, [nameMode])

  // Sync merged summary with pick mode
  useEffect(() => {
    if (!entity1 || !entity2) return
    if (summaryMode === "entityA") setMergedSummary(entity1.summary ?? "")
    else if (summaryMode === "entityB") setMergedSummary(entity2.summary ?? "")
    else
      setMergedSummary(
        [entity1.summary, entity2.summary].filter(Boolean).join("\n\n---\n\n")
      )
  }, [summaryMode])

  const handleMerge = async () => {
    if (!entity1 || !entity2) return
    if (!mergedName.trim()) {
      setError("Merged name is required.")
      return
    }
    setSaving(true)
    setError(null)
    try {
      const source = keepEntity === 1 ? entity2.key : entity1.key
      const target = keepEntity === 1 ? entity1.key : entity2.key

      const selectedFacts = facts.filter((f) => f.selected).map((f) => f.data)
      const selectedInsights = insights
        .filter((i) => i.selected)
        .map((i) => i.data)

      const properties: Record<string, unknown> = {}
      for (const cf of customFields) {
        if (cf.name.trim()) properties[cf.name.trim()] = cf.value
      }

      await graphAPI.mergeEntities(caseId, source, target, {
        name: mergedName.trim(),
        summary: mergedSummary,
        type: mergedType,
        verified_facts: selectedFacts,
        ai_insights: selectedInsights,
        properties,
      })
      onMerged?.()
      onOpenChange(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Merge failed.")
    } finally {
      setSaving(false)
    }
  }

  if (!entity1 || !entity2) return null

  const selectedFactCount = facts.filter((f) => f.selected).length
  const selectedInsightCount = insights.filter((i) => i.selected).length

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-7xl w-[90vw] max-h-[85vh] flex flex-col gap-0 p-0">
        <DialogHeader className="px-6 pt-6 pb-4">
          <div className="flex items-center gap-3">
            <DialogTitle className="text-lg">Merge Entities</DialogTitle>
            {similarity !== undefined && (
              <Badge variant="amber">
                {Math.round(similarity * 100)}% similar
              </Badge>
            )}
          </div>
        </DialogHeader>

        <ScrollArea className="flex-1 px-6">
          <div className="space-y-5 pb-4">
            {/* ── Side-by-side preview ── */}
            <div className="grid grid-cols-2 gap-3">
              <EntityPreviewCard
                entity={entity1}
                tag="Entity A"
                borderClass="border-blue-500/40"
              />
              <EntityPreviewCard
                entity={entity2}
                tag="Entity B"
                borderClass="border-emerald-500/40"
              />
            </div>

            {/* ── Swap source/target ── */}
            <div className="flex items-center gap-3">
              <span className="text-xs font-medium text-muted-foreground">
                Keep:
              </span>
              <Button
                variant={keepEntity === 1 ? "default" : "outline"}
                size="sm"
                className="text-xs"
                onClick={() => setKeepEntity(1)}
              >
                {truncate(entity1.label, 20)}
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                onClick={() => setKeepEntity(keepEntity === 1 ? 2 : 1)}
              >
                <ArrowRightLeft className="h-3.5 w-3.5" />
              </Button>
              <Button
                variant={keepEntity === 2 ? "default" : "outline"}
                size="sm"
                className="text-xs"
                onClick={() => setKeepEntity(2)}
              >
                {truncate(entity2.label, 20)}
              </Button>
              <span className="text-[10px] text-muted-foreground ml-1">
                (the other entity will be deleted)
              </span>
            </div>

            <Separator />

            {/* ── Merged Result section ── */}
            <div className="space-y-4">
              <h3 className="text-sm font-semibold">Merged Result</h3>

              {/* Name */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-medium">Name</label>
                  <PickModeToggle
                    value={nameMode}
                    onChange={setNameMode}
                    labelA={entity1.label}
                    labelB={entity2.label}
                  />
                </div>
                <Input
                  value={mergedName}
                  onChange={(e) => {
                    setMergedName(e.target.value)
                    // If user edits manually, don't auto-override
                  }}
                  placeholder="Entity name"
                />
              </div>

              {/* Type */}
              <div className="space-y-1.5">
                <label className="text-xs font-medium">Type</label>
                <Input
                  value={mergedType}
                  onChange={(e) => setMergedType(e.target.value)}
                  placeholder="Entity type"
                />
              </div>

              {/* Summary */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-medium">Summary</label>
                  <PickModeToggle
                    value={summaryMode}
                    onChange={setSummaryMode}
                    labelA={entity1.label}
                    labelB={entity2.label}
                  />
                </div>
                <Textarea
                  value={mergedSummary}
                  onChange={(e) => setMergedSummary(e.target.value)}
                  placeholder="Combined summary"
                  rows={4}
                  className="text-xs"
                />
              </div>

              {/* Verified Facts */}
              {facts.length > 0 && (
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-medium">
                      Verified Facts
                    </label>
                    <span className="text-[10px] text-muted-foreground">
                      {selectedFactCount} of {facts.length} selected
                    </span>
                  </div>
                  <div className="rounded-md border border-border max-h-40 overflow-y-auto">
                    {facts.map((item, idx) => (
                      <label
                        key={idx}
                        className={`flex items-start gap-2 px-3 py-2 text-xs cursor-pointer hover:bg-muted/50 border-b border-border last:border-b-0 ${
                          !item.selected ? "opacity-50" : ""
                        }`}
                      >
                        <Checkbox
                          checked={item.selected}
                          onCheckedChange={(checked) => {
                            setFacts((prev) =>
                              prev.map((f, i) =>
                                i === idx
                                  ? { ...f, selected: checked === true }
                                  : f
                              )
                            )
                          }}
                          className="mt-0.5"
                        />
                        <SourceBadge source={item.source} />
                        <span
                          className={
                            item.selected ? "" : "line-through"
                          }
                        >
                          {item.data.text}
                        </span>
                      </label>
                    ))}
                  </div>
                </div>
              )}

              {/* AI Insights */}
              {insights.length > 0 && (
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-medium">AI Insights</label>
                    <span className="text-[10px] text-muted-foreground">
                      {selectedInsightCount} of {insights.length} selected
                    </span>
                  </div>
                  <div className="rounded-md border border-border max-h-40 overflow-y-auto">
                    {insights.map((item, idx) => (
                      <label
                        key={idx}
                        className={`flex items-start gap-2 px-3 py-2 text-xs cursor-pointer hover:bg-muted/50 border-b border-border last:border-b-0 ${
                          !item.selected ? "opacity-50" : ""
                        }`}
                      >
                        <Checkbox
                          checked={item.selected}
                          onCheckedChange={(checked) => {
                            setInsights((prev) =>
                              prev.map((ins, i) =>
                                i === idx
                                  ? { ...ins, selected: checked === true }
                                  : ins
                              )
                            )
                          }}
                          className="mt-0.5"
                        />
                        <SourceBadge source={item.source} />
                        <span
                          className={
                            item.selected ? "" : "line-through"
                          }
                        >
                          {item.data.text}
                        </span>
                      </label>
                    ))}
                  </div>
                </div>
              )}

              {/* Custom Fields */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-medium">Custom Fields</label>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 text-xs gap-1"
                    onClick={() =>
                      setCustomFields((prev) => [
                        ...prev,
                        { name: "", value: "" },
                      ])
                    }
                  >
                    <Plus className="h-3 w-3" />
                    Add Field
                  </Button>
                </div>
                {customFields.map((cf, idx) => (
                  <div key={idx} className="flex gap-2 items-center">
                    <Input
                      value={cf.name}
                      onChange={(e) =>
                        setCustomFields((prev) =>
                          prev.map((f, i) =>
                            i === idx ? { ...f, name: e.target.value } : f
                          )
                        )
                      }
                      placeholder="Field name"
                      className="flex-1 text-xs"
                    />
                    <Input
                      value={cf.value}
                      onChange={(e) =>
                        setCustomFields((prev) =>
                          prev.map((f, i) =>
                            i === idx ? { ...f, value: e.target.value } : f
                          )
                        )
                      }
                      placeholder="Value"
                      className="flex-1 text-xs"
                    />
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 shrink-0 text-muted-foreground hover:text-destructive"
                      onClick={() =>
                        setCustomFields((prev) =>
                          prev.filter((_, i) => i !== idx)
                        )
                      }
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                ))}
              </div>
            </div>

            {/* ── Warning banner ── */}
            <div className="flex items-start gap-2.5 rounded-md border border-amber-500/30 bg-amber-500/10 p-3">
              <AlertTriangle className="h-4 w-4 shrink-0 text-amber-700 dark:text-amber-400 mt-0.5" />
              <div className="text-xs text-amber-700 dark:text-amber-400">
                <p className="font-medium">Destructive action</p>
                <p className="mt-0.5 opacity-80">
                  The source entity and its direct relationships will be merged
                  into the target. This cannot be undone.
                </p>
              </div>
            </div>

            {/* ── Error display ── */}
            {error && (
              <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
                {error}
              </div>
            )}
          </div>
        </ScrollArea>

        <DialogFooter className="px-6 py-4 border-t border-border">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={handleMerge}
            disabled={saving}
            className="gap-1.5"
          >
            <GitMerge className="h-3.5 w-3.5" />
            {saving ? "Merging…" : "Merge"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
