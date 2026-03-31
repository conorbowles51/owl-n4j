import { useState, useEffect } from "react"
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
  Camera,
  File,
} from "lucide-react"
import { useUpdateTheory, useDeleteTheory, useBuildTheoryGraph } from "../hooks/use-workspace"
import type { Theory } from "../api"

interface TheoryDetailSheetProps {
  theory: Theory | null
  open: boolean
  onOpenChange: (open: boolean) => void
  caseId: string
}

const PRIVILEGE_ICONS = {
  PUBLIC: Globe,
  ATTORNEY_ONLY: Shield,
  PRIVATE: Lock,
} as const

export function TheoryDetailSheet({ theory, open, onOpenChange, caseId }: TheoryDetailSheetProps) {
  const [title, setTitle] = useState("")
  const [type, setType] = useState<"PRIMARY" | "SECONDARY" | "NOTE">("PRIMARY")
  const [privilegeLevel, setPrivilegeLevel] = useState<"PUBLIC" | "ATTORNEY_ONLY" | "PRIVATE">("PUBLIC")
  const [confidence, setConfidence] = useState(50)
  const [hypothesis, setHypothesis] = useState("")
  const [supportingEvidence, setSupportingEvidence] = useState<string[]>([])
  const [counterArguments, setCounterArguments] = useState<string[]>([])
  const [nextSteps, setNextSteps] = useState<string[]>([])

  const updateTheory = useUpdateTheory(caseId)
  const deleteTheory = useDeleteTheory(caseId)
  const buildGraph = useBuildTheoryGraph(caseId)

  useEffect(() => {
    if (theory) {
      setTitle(theory.title ?? "")
      setType(theory.type ?? "PRIMARY")
      setPrivilegeLevel(theory.privilege_level ?? "PUBLIC")
      setConfidence(theory.confidence_score ?? 50)
      setHypothesis(theory.hypothesis ?? "")
      setSupportingEvidence(theory.supporting_evidence ?? [])
      setCounterArguments(theory.counter_arguments ?? [])
      setNextSteps(theory.next_steps ?? [])
    }
  }, [theory])

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
    buildGraph.mutate({ theoryId: theory.id })
  }

  // --- Editable list helpers ---
  const updateListItem = (
    setter: React.Dispatch<React.SetStateAction<string[]>>,
    index: number,
    value: string,
  ) => {
    setter((prev) => prev.map((item, i) => (i === index ? value : item)))
  }

  const removeListItem = (
    setter: React.Dispatch<React.SetStateAction<string[]>>,
    index: number,
  ) => {
    setter((prev) => prev.filter((_, i) => i !== index))
  }

  const addListItem = (setter: React.Dispatch<React.SetStateAction<string[]>>) => {
    setter((prev) => [...prev, ""])
  }

  const renderEditableList = (
    items: string[],
    setter: React.Dispatch<React.SetStateAction<string[]>>,
    placeholder: string,
  ) => (
    <div className="space-y-1.5">
      {items.map((item, index) => (
        <div key={index} className="flex items-center gap-1.5">
          <Input
            value={item}
            onChange={(e) => updateListItem(setter, index, e.target.value)}
            placeholder={placeholder}
            className="h-8 text-xs"
          />
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 shrink-0"
            onClick={() => removeListItem(setter, index)}
          >
            <X className="h-3.5 w-3.5" />
          </Button>
        </div>
      ))}
      <Button
        variant="outline"
        size="sm"
        className="h-7 text-xs"
        onClick={() => addListItem(setter)}
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
        { label: "Snapshots", icon: Camera, count: theory.attached_snapshot_ids?.length ?? 0 },
      ]
    : []

  const PrivilegeIcon = PRIVILEGE_ICONS[privilegeLevel]
  const graphEntities = theory?.attached_graph_data?.entities

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="flex w-full flex-col sm:max-w-lg">
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
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Theory title"
              />
              <div className="flex items-center gap-2">
                <Select value={type} onValueChange={(v) => setType(v as typeof type)}>
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
                  onValueChange={(v) => setPrivilegeLevel(v as typeof privilegeLevel)}
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
                onValueChange={(vals) => setConfidence(vals[0])}
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
                onChange={(e) => setHypothesis(e.target.value)}
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
              {renderEditableList(supportingEvidence, setSupportingEvidence, "Add supporting evidence...")}
            </div>

            {/* Counter Arguments */}
            <div className="space-y-2">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Counter Arguments
              </h4>
              {renderEditableList(counterArguments, setCounterArguments, "Add counter argument...")}
            </div>

            {/* Next Steps */}
            <div className="space-y-2">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Next Steps
              </h4>
              {renderEditableList(nextSteps, setNextSteps, "Add next step...")}
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
