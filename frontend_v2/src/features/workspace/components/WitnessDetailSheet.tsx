import { useState, useEffect, useMemo } from "react"
import { useNavigate } from "react-router-dom"
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Save, Trash2, Star, Network, Loader2 } from "lucide-react"
import { useUpdateWitness, useDeleteWitness, useBuildWorkspaceGraph } from "../hooks/use-workspace"
import type { Witness } from "../api"
import { formatWorkspaceDate } from "../lib/format-date"

interface WitnessDetailSheetProps {
  witness: Witness | null
  open: boolean
  onOpenChange: (open: boolean) => void
  caseId: string
}

const categoryBadge = (category: string) => {
  switch (category) {
    case "FRIENDLY":
      return (
        <Badge className="bg-emerald-500/10 text-emerald-500 border-emerald-500/20">
          Friendly
        </Badge>
      )
    case "ADVERSE":
      return (
        <Badge className="bg-red-500/10 text-red-500 border-red-500/20">
          Adverse
        </Badge>
      )
    default:
      return <Badge variant="secondary">Neutral</Badge>
  }
}

export function WitnessDetailSheet({
  witness,
  open,
  onOpenChange,
  caseId,
}: WitnessDetailSheetProps) {
  const navigate = useNavigate()
  const [name, setName] = useState("")
  const [role, setRole] = useState("")
  const [organization, setOrganization] = useState("")
  const [category, setCategory] = useState<"FRIENDLY" | "NEUTRAL" | "ADVERSE">(
    "NEUTRAL",
  )
  const [credibilityRating, setCredibilityRating] = useState(0)
  const [statementSummary, setStatementSummary] = useState("")
  const [riskAssessment, setRiskAssessment] = useState("")
  const [strategyNotes, setStrategyNotes] = useState("")

  const updateWitness = useUpdateWitness(caseId)
  const deleteWitness = useDeleteWitness(caseId)
  const buildGraph = useBuildWorkspaceGraph(caseId)

  useEffect(() => {
    if (witness) {
      setName(witness.name ?? "")
      setRole(witness.role ?? "")
      setOrganization(witness.organization ?? "")
      setCategory(witness.category ?? "NEUTRAL")
      setCredibilityRating(witness.credibility_rating ?? 0)
      setStatementSummary(witness.statement_summary ?? "")
      setRiskAssessment(witness.risk_assessment ?? "")
      setStrategyNotes(witness.strategy_notes ?? "")
    }
  }, [witness])

  const isDirty = useMemo(
    () =>
      !!witness &&
      (name !== (witness.name ?? "") ||
        role !== (witness.role ?? "") ||
        organization !== (witness.organization ?? "") ||
        category !== (witness.category ?? "NEUTRAL") ||
        credibilityRating !== (witness.credibility_rating ?? 0) ||
        statementSummary !== (witness.statement_summary ?? "") ||
        riskAssessment !== (witness.risk_assessment ?? "") ||
        strategyNotes !== (witness.strategy_notes ?? "")),
    [category, credibilityRating, name, organization, riskAssessment, role, statementSummary, strategyNotes, witness],
  )

  const handleSave = () => {
    if (!witness) return
    updateWitness.mutate(
      {
        witnessId: witness.id,
        updates: {
          name,
          role,
          organization,
          category,
          credibility_rating: credibilityRating,
          statement_summary: statementSummary,
          risk_assessment: riskAssessment,
          strategy_notes: strategyNotes,
        },
      },
      { onSuccess: () => onOpenChange(false) },
    )
  }

  const handleDelete = () => {
    if (!witness) return
    if (!window.confirm("Are you sure you want to delete this witness?")) return
    deleteWitness.mutate(witness.id, {
      onSuccess: () => onOpenChange(false),
    })
  }

  const handleBuildGraph = () => {
    if (!witness) return
    buildGraph.mutate(
      {
        source_type: "witness",
        source_id: witness.id,
      },
      {
        onSuccess: (result) => {
          navigate(`/cases/${caseId}/graph`, {
            state: {
              workspaceGraphSource: {
                sourceType: "witness",
                sourceId: witness.id,
                sourceLabel: witness.name,
                entityKeys: result.entity_keys,
              },
            },
          })
        },
      },
    )
  }

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
        className="w-full sm:max-w-lg flex flex-col"
        onInteractOutside={(event) => {
          if (isDirty) event.preventDefault()
        }}
        onEscapeKeyDown={(event) => {
          if (isDirty) event.preventDefault()
        }}
      >
        <SheetHeader>
          <SheetTitle>Witness Details</SheetTitle>
          <SheetDescription>
            View and edit witness information.
          </SheetDescription>
        </SheetHeader>

        <ScrollArea className="flex-1 px-4">
          <div className="space-y-6 py-4">
            {/* Name */}
            <div className="space-y-2">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Name
              </h4>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Witness name"
              />
            </div>

            {/* Role */}
            <div className="space-y-2">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Role
              </h4>
              <Input
                value={role}
                onChange={(e) => setRole(e.target.value)}
                placeholder="Role or title"
              />
            </div>

            {/* Organization */}
            <div className="space-y-2">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Organization
              </h4>
              <Input
                value={organization}
                onChange={(e) => setOrganization(e.target.value)}
                placeholder="Organization"
              />
            </div>

            {/* Category */}
            <div className="space-y-2">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Category
              </h4>
              <div className="flex items-center gap-3">
                <Select
                  value={category}
                  onValueChange={(v) =>
                    setCategory(v as "FRIENDLY" | "NEUTRAL" | "ADVERSE")
                  }
                >
                  <SelectTrigger className="w-[180px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="FRIENDLY">Friendly</SelectItem>
                    <SelectItem value="NEUTRAL">Neutral</SelectItem>
                    <SelectItem value="ADVERSE">Adverse</SelectItem>
                  </SelectContent>
                </Select>
                {categoryBadge(category)}
              </div>
            </div>

            {/* Credibility Rating */}
            <div className="space-y-2">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Credibility Rating
              </h4>
              <div className="flex items-center gap-1">
                {[1, 2, 3, 4, 5].map((star) => (
                  <button
                    key={star}
                    type="button"
                    onClick={() => setCredibilityRating(star)}
                    className="p-0.5 hover:scale-110 transition-transform"
                  >
                    <Star
                      className={
                        star <= credibilityRating
                          ? "h-5 w-5 text-amber-400 fill-amber-400"
                          : "h-5 w-5 text-muted-foreground"
                      }
                    />
                  </button>
                ))}
              </div>
            </div>

            {/* Statement Summary */}
            <div className="space-y-2">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Statement Summary
              </h4>
              <Textarea
                value={statementSummary}
                onChange={(e) => setStatementSummary(e.target.value)}
                placeholder="Summary of witness statement..."
                rows={3}
              />
            </div>

            {/* Risk Assessment */}
            <div className="space-y-2">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Risk Assessment
              </h4>
              <Textarea
                value={riskAssessment}
                onChange={(e) => setRiskAssessment(e.target.value)}
                placeholder="Assess risks related to this witness..."
                rows={3}
              />
            </div>

            {/* Strategy Notes */}
            <div className="space-y-2">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Strategy Notes
              </h4>
              <Textarea
                value={strategyNotes}
                onChange={(e) => setStrategyNotes(e.target.value)}
                placeholder="Notes on examination strategy..."
                rows={3}
              />
            </div>

            {/* Interviews */}
            <div className="space-y-2">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Interviews
              </h4>
              {witness?.interviews && witness.interviews.length > 0 ? (
                <div className="space-y-2">
                  {witness.interviews.map((interview, idx) => (
                    <div
                      key={interview.interview_id ?? idx}
                      className="rounded-md border p-3 text-sm space-y-1"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-medium">
                          {formatWorkspaceDate(interview.date)}
                        </span>
                        {interview.status && (
                          <Badge variant="outline">{interview.status}</Badge>
                        )}
                      </div>
                      {interview.duration && (
                        <p className="text-muted-foreground text-xs">
                          Duration: {interview.duration}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">
                  No interviews recorded
                </p>
              )}
            </div>
          </div>
        </ScrollArea>

        <SheetFooter className="flex flex-row gap-2 px-4 py-4 border-t">
          <Button
            variant="danger"
            size="sm"
            onClick={handleDelete}
            disabled={deleteWitness.isPending}
          >
            <Trash2 className="h-4 w-4 mr-1" />
            Delete
          </Button>
          <div className="flex-1" />
          <Button
            variant="outline"
            size="sm"
            onClick={handleBuildGraph}
            disabled={buildGraph.isPending}
          >
            {buildGraph.isPending ? (
              <Loader2 className="h-4 w-4 mr-1 animate-spin" />
            ) : (
              <Network className="h-4 w-4 mr-1" />
            )}
            Build Graph
          </Button>
          <Button
            size="sm"
            onClick={handleSave}
            disabled={updateWitness.isPending}
          >
            <Save className="h-4 w-4 mr-1" />
            Save
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  )
}
