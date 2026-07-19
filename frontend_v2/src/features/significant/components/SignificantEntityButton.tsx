import { Star, StarOff } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/cn"
import {
  useAddSignificantEntities,
  useRemoveSignificantEntities,
  useSignificantManifest,
} from "../hooks/use-significant"

interface SignificantEntityButtonProps {
  caseId: string
  entityKey: string
  surface: string
  compact?: boolean
  className?: string
  onChanged?: (significant: boolean) => void
}

export function SignificantEntityButton({
  caseId,
  entityKey,
  surface,
  compact = false,
  className,
  onChanged,
}: SignificantEntityButtonProps) {
  const { entityKeySet, isLoading } = useSignificantManifest(caseId)
  const addEntities = useAddSignificantEntities(caseId)
  const removeEntities = useRemoveSignificantEntities(caseId)
  const isSignificant = entityKeySet.has(entityKey)
  const pending = isLoading || addEntities.isPending || removeEntities.isPending

  const toggle = async () => {
    try {
      if (isSignificant) {
        const result = await removeEntities.mutateAsync([entityKey])
        if ((result.removed_count ?? 0) > 0) {
          toast.success("Removed from Significant")
          onChanged?.(false)
        }
      } else {
        const result = await addEntities.mutateAsync({
          entityKeys: [entityKey],
          source: "manual",
          context: { surface },
        })
        if ((result.added_count ?? 0) > 0) {
          toast.success("Added to Significant")
          onChanged?.(true)
        } else if ((result.missing_count ?? 0) > 0) {
          toast.error("This entity is no longer available")
        }
      }
    } catch (error) {
      toast.error(
        error instanceof Error
          ? error.message
          : "Could not update the Significant layer"
      )
    }
  }

  return (
    <Button
      type="button"
      variant={isSignificant ? "secondary" : "outline"}
      size={compact ? "icon-sm" : "sm"}
      className={cn(
        isSignificant &&
          "border-amber-500/30 bg-amber-500/10 text-amber-700 hover:bg-amber-500/15 dark:text-amber-300",
        className
      )}
      disabled={pending}
      aria-pressed={isSignificant}
      aria-label={
        isSignificant ? "Remove from Significant" : "Add to Significant"
      }
      title={
        isSignificant ? "Remove from Significant" : "Add to Significant"
      }
      onClick={(event) => {
        event.stopPropagation()
        void toggle()
      }}
    >
      {isSignificant ? (
        <StarOff className="size-3.5" />
      ) : (
        <Star className="size-3.5" />
      )}
      {compact ? null : isSignificant ? "Remove from Significant" : "Add to Significant"}
    </Button>
  )
}
