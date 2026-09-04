import {
  CheckCircle2,
  CircleHelp,
  Info,
  MinusCircle,
  Sparkles,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/cn"
import type { CaseworkEntry, LinkRelationship } from "../casework-api"
import { RELATIONSHIP_LABELS } from "../casework-utils"

const relationshipIcons = {
  unclassified: CircleHelp,
  supports: CheckCircle2,
  contradicts: MinusCircle,
  context: Info,
}

export function RelationshipBadge({
  relationship = "unclassified",
  className,
}: {
  relationship?: LinkRelationship
  className?: string
}) {
  const Icon = relationshipIcons[relationship]
  return (
    <Badge
      variant="outline"
      className={cn(
        "gap-1 border-border bg-background px-1.5 py-0 text-[10px] font-medium text-muted-foreground",
        relationship === "supports" && "border-emerald-300 text-emerald-800 dark:border-emerald-800 dark:text-emerald-300",
        relationship === "contradicts" && "border-rose-300 text-rose-800 dark:border-rose-800 dark:text-rose-300",
        relationship === "context" && "border-sky-300 text-sky-800 dark:border-sky-800 dark:text-sky-300",
        className,
      )}
    >
      <Icon className="size-3" aria-hidden="true" />
      {RELATIONSHIP_LABELS[relationship]}
    </Badge>
  )
}

export function ReviewBadge({ entry }: { entry: CaseworkEntry }) {
  if (entry.review_state !== "pending") return null
  return (
    <Badge className="gap-1 border-violet-300 bg-violet-50 text-violet-800 dark:border-violet-800 dark:bg-violet-950/45 dark:text-violet-200" variant="outline">
      <Sparkles className="size-3" /> Pending human review
    </Badge>
  )
}
