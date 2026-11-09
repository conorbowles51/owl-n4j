import { Star, StarOff } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/cn"
import {
  relationshipMarkKey,
  useSignificantManifest,
  useToggleSignificantRelationship,
} from "../hooks/use-significant"
import type { RelationshipRef } from "../types"

interface SignificantRelationshipButtonProps {
  caseId: string
  relationship: RelationshipRef
  surface: string
  /** Words for the relationship in labels, e.g. "Ann Director of Acme". */
  description?: string
  compact?: boolean
  className?: string
  onChanged?: (significant: boolean) => void
}

/** Mark or unmark one relationship significant (GR-01), beside the entity button. */
export function SignificantRelationshipButton({
  caseId,
  relationship,
  surface,
  description,
  compact = false,
  className,
  onChanged,
}: SignificantRelationshipButtonProps) {
  const { relationshipKeySet, isLoading } = useSignificantManifest(caseId)
  const toggle = useToggleSignificantRelationship(caseId)
  const isSignificant = relationshipKeySet.has(
    relationshipMarkKey(relationship.source_key, relationship.type, relationship.target_key)
  )
  const label = isSignificant ? "Remove relationship from Significant" : "Mark relationship significant"
  const fullLabel = description ? `${label}: ${description}` : label

  const run = async () => {
    try {
      const result = await toggle.mutateAsync({ relationship, significant: !isSignificant, surface })
      if (isSignificant) {
        if ((result.removed_relationship_count ?? 0) > 0) {
          toast.success("Relationship removed from Significant")
          onChanged?.(false)
        }
      } else if ((result.added_relationship_count ?? 0) > 0) {
        toast.success("Relationship marked significant")
        onChanged?.(true)
      } else if ((result.missing_relationship_count ?? 0) > 0) {
        toast.error("This relationship is no longer in the graph")
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not update the Significant layer")
    }
  }

  return (
    <Button
      type="button"
      variant="ghost"
      size={compact ? "icon-sm" : "sm"}
      className={cn(isSignificant && "text-amber-600 dark:text-amber-300", className)}
      disabled={isLoading || toggle.isPending}
      aria-pressed={isSignificant}
      aria-label={fullLabel}
      title={label}
      onClick={(event) => {
        event.stopPropagation()
        void run()
      }}
    >
      {isSignificant ? <StarOff className="size-3.5" /> : <Star className="size-3.5" />}
      {compact ? null : label}
    </Button>
  )
}
