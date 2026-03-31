import { useState } from "react"
import { Users, Plus, Star } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { cn } from "@/lib/cn"
import { useWitnesses, useCreateWitness } from "../hooks/use-workspace"
import type { Witness } from "../api"
import { WitnessDetailSheet } from "./WitnessDetailSheet"

interface WitnessMatrixSectionProps {
  caseId: string
}

const CATEGORY_STYLE: Record<string, { label: string; className: string }> = {
  FRIENDLY: { label: "Friendly", className: "bg-emerald-500/10 text-emerald-500 border-emerald-500/20" },
  NEUTRAL: { label: "Neutral", className: "" },
  ADVERSE: { label: "Adverse", className: "bg-red-500/10 text-red-500 border-red-500/20" },
}

const CATEGORY_ORDER = ["FRIENDLY", "NEUTRAL", "ADVERSE", "UNCATEGORIZED"] as const

function groupByCategory(witnesses: Witness[]) {
  const groups: Record<string, Witness[]> = {}
  for (const cat of CATEGORY_ORDER) groups[cat] = []
  for (const w of witnesses) {
    const cat = w.category?.toUpperCase() ?? "UNCATEGORIZED"
    const key = CATEGORY_ORDER.includes(cat as (typeof CATEGORY_ORDER)[number]) ? cat : "UNCATEGORIZED"
    groups[key].push(w)
  }
  return groups
}

function CredibilityStars({ rating }: { rating: number }) {
  return (
    <div className="flex gap-0.5">
      {[1, 2, 3, 4, 5].map((i) => (
        <Star
          key={i}
          className={cn(
            "size-2.5",
            i <= rating ? "fill-amber-400 text-amber-400" : "text-muted-foreground/30",
          )}
        />
      ))}
    </div>
  )
}

export function WitnessMatrixSection({ caseId }: WitnessMatrixSectionProps) {
  const { data: witnesses = [], isLoading } = useWitnesses(caseId)
  const createMutation = useCreateWitness(caseId)

  const [showAdd, setShowAdd] = useState(false)
  const [name, setName] = useState("")
  const [role, setRole] = useState("")
  const [category, setCategory] = useState<string>("NEUTRAL")

  const [selectedWitnessId, setSelectedWitnessId] = useState<string | null>(null)
  const [detailOpen, setDetailOpen] = useState(false)

  const selectedWitness = selectedWitnessId
    ? witnesses.find((w) => w.id === selectedWitnessId) ?? null
    : null

  const handleAdd = () => {
    if (!name.trim()) return
    createMutation.mutate(
      { name, role, category: category as Witness["category"] },
      {
        onSuccess: () => {
          setShowAdd(false)
          setName("")
          setRole("")
          setCategory("NEUTRAL")
        },
      },
    )
  }

  const openDetail = (w: Witness) => {
    setSelectedWitnessId(w.id)
    setDetailOpen(true)
  }

  const grouped = groupByCategory(witnesses)

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Users className="size-4 text-violet-500" />
          <h2 className="text-sm font-semibold">Witnesses</h2>
          <Badge variant="slate" className="h-5 px-1.5 text-[10px]">
            {witnesses.length}
          </Badge>
        </div>
        <Button variant="outline" size="sm" onClick={() => setShowAdd(!showAdd)}>
          <Plus className="mr-1 size-3" />
          Add Witness
        </Button>
      </div>

      {/* Add form */}
      {showAdd && (
        <div className="flex items-center gap-2 rounded-lg border border-border p-2.5">
          <Input
            placeholder="Name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="h-7 flex-1 text-xs"
          />
          <Input
            placeholder="Role"
            value={role}
            onChange={(e) => setRole(e.target.value)}
            className="h-7 w-32 text-xs"
          />
          <Select value={category} onValueChange={setCategory}>
            <SelectTrigger className="h-7 w-28 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="FRIENDLY">Friendly</SelectItem>
              <SelectItem value="NEUTRAL">Neutral</SelectItem>
              <SelectItem value="ADVERSE">Adverse</SelectItem>
            </SelectContent>
          </Select>
          <Button
            variant="primary"
            size="sm"
            onClick={handleAdd}
            disabled={!name.trim() || createMutation.isPending}
          >
            Add
          </Button>
          <Button variant="ghost" size="sm" onClick={() => setShowAdd(false)}>
            Cancel
          </Button>
        </div>
      )}

      {/* Witness groups */}
      {isLoading ? (
        <div className="space-y-2">
          {[1, 2].map((i) => (
            <div key={i} className="h-12 animate-pulse rounded-md bg-muted/30" />
          ))}
        </div>
      ) : witnesses.length === 0 ? (
        <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-border py-8">
          <Users className="size-8 text-muted-foreground/40" />
          <p className="text-xs text-muted-foreground">No witnesses added</p>
        </div>
      ) : (
        <div className="space-y-4">
          {CATEGORY_ORDER.map((cat) => {
            const group = grouped[cat]
            if (group.length === 0) return null
            const style = CATEGORY_STYLE[cat]

            return (
              <div key={cat} className="space-y-1">
                <div className="flex items-center gap-1.5 pb-1">
                  {style ? (
                    <Badge variant="outline" className={cn("text-[10px]", style.className)}>
                      {style.label}
                    </Badge>
                  ) : (
                    <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                      Uncategorized
                    </span>
                  )}
                  <span className="text-[10px] text-muted-foreground/60">{group.length}</span>
                </div>
                {group.map((w) => (
                  <button
                    key={w.id}
                    onClick={() => openDetail(w)}
                    className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left hover:bg-muted/30"
                  >
                    <Users className="size-3 shrink-0 text-muted-foreground" />
                    <span className="flex-1 text-xs font-medium">{w.name}</span>
                    {w.role && (
                      <Badge variant="outline" className="text-[10px]">
                        {w.role}
                      </Badge>
                    )}
                    {w.organization && (
                      <span className="max-w-24 truncate text-[10px] text-muted-foreground">
                        {w.organization}
                      </span>
                    )}
                    {w.credibility_rating != null && w.credibility_rating > 0 && (
                      <CredibilityStars rating={w.credibility_rating} />
                    )}
                  </button>
                ))}
              </div>
            )
          })}
        </div>
      )}

      {/* Detail sheet */}
      <WitnessDetailSheet
        witness={selectedWitness}
        open={detailOpen}
        onOpenChange={setDetailOpen}
        caseId={caseId}
      />
    </div>
  )
}
