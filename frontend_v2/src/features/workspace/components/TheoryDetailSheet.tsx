import { useMemo, useState } from "react"
import { useNavigate } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
  SheetFooter,
} from "@/components/ui/sheet"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Slider } from "@/components/ui/slider"
import { ConfidenceBar } from "@/components/ui/confidence-bar"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Save,
  Trash2,
  Plus,
  X,
  Network,
  Loader2,
  Lock,
  Shield,
  Globe,
  FileText,
  Users,
  StickyNote,
  CheckSquare,
  File,
} from "lucide-react"
import { useUpdateTheory, useDeleteTheory, useBuildWorkspaceGraph } from "../hooks/use-workspace"
import { workspaceAPI, type Theory } from "../api"
import { formatWorkspaceDateTime } from "../lib/format-date"

interface TheoryDetailSheetProps {
  theory: Theory | null
  open: boolean
  onOpenChange: (open: boolean) => void
  caseId: string
}

type TheoryType = NonNullable<Theory["type"]>
type PrivilegeLevel = NonNullable<Theory["privilege_level"]>
type TheoryListField = "supportingEvidence" | "counterArguments" | "nextSteps"

interface TheoryDraft {
  sourceKey: string
  title: string
  type: TheoryType
  privilegeLevel: PrivilegeLevel
  confidence: number
  hypothesis: string
  supportingEvidence: string[]
  counterArguments: string[]
  nextSteps: string[]
}

function createTheoryDraft(theory: Theory | null): TheoryDraft {
  if (!theory) {
    return {
      sourceKey: "__empty__",
      title: "",
      type: "PRIMARY",
      privilegeLevel: "PUBLIC",
      confidence: 50,
      hypothesis: "",
      supportingEvidence: [],
      counterArguments: [],
      nextSteps: [],
    }
  }

  return {
    sourceKey: JSON.stringify([
      theory.id,
      theory.title ?? "",
      theory.type ?? "PRIMARY",
      theory.privilege_level ?? "PUBLIC",
      theory.confidence_score ?? 50,
      theory.hypothesis ?? "",
      theory.supporting_evidence ?? [],
      theory.counter_arguments ?? [],
      theory.next_steps ?? [],
    ]),
    title: theory.title ?? "",
    type: theory.type ?? "PRIMARY",
    privilegeLevel: theory.privilege_level ?? "PUBLIC",
    confidence: theory.confidence_score ?? 50,
    hypothesis: theory.hypothesis ?? "",
    supportingEvidence: [...(theory.supporting_evidence ?? [])],
    counterArguments: [...(theory.counter_arguments ?? [])],
    nextSteps: [...(theory.next_steps ?? [])],
  }
}

const PRIVILEGE_ICONS = {
  PUBLIC: Globe,
  ATTORNEY_ONLY: Shield,
  PRIVATE: Lock,
} as const

export function TheoryDetailSheet({ theory, open, onOpenChange, caseId }: TheoryDetailSheetProps) {
  const navigate = useNavigate()
  const updateTheory = useUpdateTheory(caseId)
  const deleteTheory = useDeleteTheory(caseId)
  const buildGraph = useBuildWorkspaceGraph(caseId)

  const sourceDraft = useMemo(() => createTheoryDraft(theory), [theory])
  const [draft, setDraft] = useState(sourceDraft)
  const activeDraft =
    draft.sourceKey === sourceDraft.sourceKey ? draft : sourceDraft
  const {
    title,
    type,
    privilegeLevel,
    confidence,
    hypothesis,
    supportingEvidence,
    counterArguments,
    nextSteps,
  } = activeDraft
  const updateDraft = (updates: Partial<Omit<TheoryDraft, "sourceKey">>) => {
    setDraft((current) => ({
      ...(current.sourceKey === sourceDraft.sourceKey ? current : sourceDraft),
      ...updates,
    }))
  }

  const isDirty = useMemo(
    () =>
      !!theory &&
      (title !== (theory.title ?? "") ||
        type !== (theory.type ?? "PRIMARY") ||
        privilegeLevel !== (theory.privilege_level ?? "PUBLIC") ||
        confidence !== (theory.confidence_score ?? 50) ||
        hypothesis !== (theory.hypothesis ?? "") ||
        JSON.stringify(supportingEvidence) !== JSON.stringify(theory.supporting_evidence ?? []) ||
        JSON.stringify(counterArguments) !== JSON.stringify(theory.counter_arguments ?? []) ||
        JSON.stringify(nextSteps) !== JSON.stringify(theory.next_steps ?? [])),
    [confidence, counterArguments, hypothesis, nextSteps, privilegeLevel, supportingEvidence, theory, title, type],
  )

  const { data: theoryTimeline = [] } = useQuery({
    queryKey: ["workspace", caseId, "theory-timeline", theory?.id],
    queryFn: () => workspaceAPI.getTheoryTimeline(caseId, theory!.id),
    enabled: open && !!theory?.id,
  })

  const handleSave = () => {
    if (!theory) return
    updateTheory.mutate(
      {
        theoryId: theory.id,
        updates: {
          title,
          type,
          privilege_level: privilegeLevel,
          confidence_score: confidence,
          hypothesis,
          supporting_evidence: supportingEvidence,
          counter_arguments: counterArguments,
          next_steps: nextSteps,
        },
      },
      { onSuccess: () => onOpenChange(false) },
    )
  }

  const handleDelete = () => {
    if (!theory) return
    if (!window.confirm("Are you sure you want to delete this theory? This action cannot be undone.")) return
    deleteTheory.mutate(theory.id, {
      onSuccess: () => onOpenChange(false),
    })
  }

  const handleBuildGraph = () => {
    if (!theory) return
    buildGraph.mutate(
      { source_type: "theory", source_id: theory.id },
      {
        onSuccess: (result) => {
          navigate(`/cases/${caseId}/graph`, {
            state: {
              workspaceGraphSource: {
                sourceType: "theory",
                sourceId: theory.id,
                sourceLabel: theory.title,
                entityKeys: result.entity_keys,
              },
            },
          })
        },
      },
    )
  }

  // --- Editable list helpers ---
  const updateListItem = (
    field: TheoryListField,
    index: number,
    value: string,
  ) => {
    updateDraft({
      [field]: activeDraft[field].map((item, i) =>
        i === index ? value : item
      ),
    })
  }

  const removeListItem = (
    field: TheoryListField,
    index: number,
  ) => {
    updateDraft({
      [field]: activeDraft[field].filter((_, i) => i !== index),
    })
  }

  const addListItem = (field: TheoryListField) => {
    updateDraft({ [field]: [...activeDraft[field], ""] })
  }

  const renderEditableList = (
    items: string[],
    field: TheoryListField,
    placeholder: string,
  ) => (
    <div className="space-y-1.5">
      {items.map((item, index) => (
        <div key={index} className="flex items-center gap-1.5">
          <Input
            value={item}
            onChange={(e) => updateListItem(field, index, e.target.value)}
            placeholder={placeholder}
            className="h-8 text-xs"
          />
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 shrink-0"
            onClick={() => removeListItem(field, index)}
          >
            <X className="h-3.5 w-3.5" />
          </Button>
        </div>
      ))}
      <Button
        variant="outline"
        size="sm"
        className="h-7 text-xs"
        onClick={() => addListItem(field)}
      >
        <Plus className="mr-1 h-3 w-3" />
        Add
      </Button>
    </div>
  )

  // --- Attached item counts ---
  const attachedCounts = theory
    ? [
        { label: "Evidence", icon: FileText, count: theory.attached_evidence_ids?.length ?? 0 },
        { label: "Witnesses", icon: Users, count: theory.attached_witness_ids?.length ?? 0 },
        { label: "Notes", icon: StickyNote, count: theory.attached_note_ids?.length ?? 0 },
        { label: "Tasks", icon: CheckSquare, count: theory.attached_task_ids?.length ?? 0 },
        { label: "Documents", icon: File, count: theory.attached_document_ids?.length ?? 0 },
      ]
    : []

  const PrivilegeIcon = PRIVILEGE_ICONS[privilegeLevel]
  const graphEntities = theory?.attached_graph_data?.entities

  return (
    <Sheet
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen && isDirty) return
        onOpenChange(nextOpen)
      }}
    >
      <SheetContent
        side="right"
        className="flex w-full flex-col sm:max-w-lg"
        onInteractOutside={(event) => {
          if (isDirty) event.preventDefault()
        }}
        onEscapeKeyDown={(event) => {
          if (isDirty) event.preventDefault()
        }}
      >
        <SheetHeader className="px-4 pt-4">
          <SheetTitle className="sr-only">Theory Details</SheetTitle>
          <SheetDescription className="sr-only">
            View and edit theory details
          </SheetDescription>
        </SheetHeader>

        <ScrollArea className="flex-1 px-4">
          <div className="space-y-6 py-4">
            {/* Header: Title, Type, Privilege */}
            <div className="space-y-2">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Title
              </h4>
              <Input
                value={title}
                onChange={(e) => updateDraft({ title: e.target.value })}
                placeholder="Theory title"
              />
              <div className="flex items-center gap-2">
                <Select
                  value={type}
                  onValueChange={(v) => updateDraft({ type: v as TheoryType })}
                >
                  <SelectTrigger className="h-8 w-[140px] text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="PRIMARY">Primary</SelectItem>
                    <SelectItem value="SECONDARY">Secondary</SelectItem>
                    <SelectItem value="NOTE">Note</SelectItem>
                  </SelectContent>
                </Select>

                <Select
                  value={privilegeLevel}
                  onValueChange={(v) =>
                    updateDraft({ privilegeLevel: v as PrivilegeLevel })
                  }
                >
                  <SelectTrigger className="h-8 w-[160px] text-xs">
                    <div className="flex items-center gap-1.5">
                      <PrivilegeIcon className="h-3.5 w-3.5" />
                      <SelectValue />
                    </div>
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="PUBLIC">
                      <div className="flex items-center gap-1.5">
                        <Globe className="h-3.5 w-3.5" />
                        Public
                      </div>
                    </SelectItem>
                    <SelectItem value="ATTORNEY_ONLY">
                      <div className="flex items-center gap-1.5">
                        <Shield className="h-3.5 w-3.5" />
                        Attorney Only
                      </div>
                    </SelectItem>
                    <SelectItem value="PRIVATE">
                      <div className="flex items-center gap-1.5">
                        <Lock className="h-3.5 w-3.5" />
                        Private
                      </div>
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            {/* Confidence */}
            <div className="space-y-2">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Confidence
              </h4>
              <Slider
                value={[confidence]}
                onValueChange={(vals) => updateDraft({ confidence: vals[0] })}
                min={0}
                max={100}
                step={1}
              />
              <ConfidenceBar value={confidence / 100} />
            </div>

            {/* Hypothesis */}
            <div className="space-y-2">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Hypothesis
              </h4>
              <Textarea
                value={hypothesis}
                onChange={(e) => updateDraft({ hypothesis: e.target.value })}
                placeholder="Describe the theory hypothesis..."
                rows={4}
                className="text-sm"
              />
            </div>

            {/* Supporting Evidence */}
            <div className="space-y-2">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Supporting Evidence
              </h4>
              {renderEditableList(supportingEvidence, "supportingEvidence", "Add supporting evidence...")}
            </div>

            {/* Counter Arguments */}
            <div className="space-y-2">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Counter Arguments
              </h4>
              {renderEditableList(counterArguments, "counterArguments", "Add counter argument...")}
            </div>

            {/* Next Steps */}
            <div className="space-y-2">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Next Steps
              </h4>
              {renderEditableList(nextSteps, "nextSteps", "Add next step...")}
            </div>

            {/* Attached Items */}
            <div className="space-y-2">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Attached Items
              </h4>
              <div className="space-y-1">
                {attachedCounts.map(({ label, icon: Icon, count }) => (
                  <div
                    key={label}
                    className="flex items-center justify-between rounded-md border border-border px-2.5 py-1.5"
                  >
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <Icon className="h-3.5 w-3.5" />
                      <span>{label}</span>
                    </div>
                    <span className="font-mono text-xs text-muted-foreground">{count}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Theory Graph */}
            <div className="space-y-2">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Theory Graph
              </h4>
              {graphEntities && graphEntities.length > 0 ? (
                <div className="space-y-1.5">
                  {graphEntities.map((entity) => (
                    <div
                      key={entity.key}
                      className="flex items-center justify-between rounded-md border border-border px-2.5 py-1.5"
                    >
                      <div className="flex items-center gap-2">
                        <Badge variant="outline" className="text-[10px]">
                          {entity.type}
                        </Badge>
                        <span className="text-xs font-medium">{entity.name}</span>
                      </div>
                      <span className="font-mono text-[10px] text-muted-foreground">
                        {Math.round((1 - entity.distance) * 100)}%
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <Button
                  variant="outline"
                  size="sm"
                  className="w-full text-xs"
                  onClick={handleBuildGraph}
                  disabled={buildGraph.isPending}
                >
                  {buildGraph.isPending ? (
                    <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Network className="mr-1.5 h-3.5 w-3.5" />
                  )}
                  Build Graph
                </Button>
              )}
            </div>

            <div className="space-y-2">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Timeline
              </h4>
              {theoryTimeline.length === 0 ? (
                <p className="text-xs text-muted-foreground">No timeline events yet</p>
              ) : (
                <div className="space-y-2">
                  {theoryTimeline.slice().reverse().slice(0, 6).map((event) => (
                    <div key={event.id} className="rounded-md border border-border px-2.5 py-2">
                      <p className="text-xs font-medium">{event.title}</p>
                      <p className="mt-1 text-[10px] text-muted-foreground">
                        {formatWorkspaceDateTime(event.date)}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </ScrollArea>

        <SheetFooter className="flex-row gap-2 border-t px-4 py-3">
          <Button
            variant="danger"
            size="sm"
            onClick={handleDelete}
            disabled={deleteTheory.isPending}
          >
            {deleteTheory.isPending ? (
              <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
            ) : (
              <Trash2 className="mr-1.5 h-3.5 w-3.5" />
            )}
            Delete
          </Button>
          <Button
            size="sm"
            onClick={handleSave}
            disabled={updateTheory.isPending}
          >
            {updateTheory.isPending ? (
              <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
            ) : (
              <Save className="mr-1.5 h-3.5 w-3.5" />
            )}
            Save
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  )
}
