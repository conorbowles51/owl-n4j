import type { LucideIcon } from "lucide-react"
import { ArrowLeft, Star } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useSignificantManifest } from "../hooks/use-significant"
import { useCaseLayerStore } from "../stores/case-layer.store"

interface SignificantEmptyStateProps {
  caseId: string
  icon: LucideIcon
  eligibleTitle: string
  eligibleDescription: string
}

export function SignificantEmptyState({
  caseId,
  icon: Icon,
  eligibleTitle,
  eligibleDescription,
}: SignificantEmptyStateProps) {
  const { data } = useSignificantManifest(caseId)
  const setLayer = useCaseLayerStore((state) => state.setLayer)
  const hasSignificantEntities = (data?.count ?? 0) > 0

  return (
    <div className="relative flex h-full items-center justify-center overflow-hidden bg-canvas px-6">
      <div className="pointer-events-none absolute inset-0 opacity-50 [background-image:radial-gradient(circle_at_center,rgba(217,119,6,0.09)_0,transparent_48%)]" />
      <div className="relative max-w-md text-center">
        <div className="mx-auto mb-4 grid size-14 place-items-center rounded-2xl border border-amber-500/25 bg-amber-500/10 text-amber-600 shadow-[0_16px_50px_-28px_rgba(217,119,6,0.75)] dark:text-amber-300">
          {hasSignificantEntities ? (
            <Icon className="size-6" />
          ) : (
            <Star className="size-6" />
          )}
        </div>
        <h2 className="text-base font-semibold text-foreground">
          {hasSignificantEntities ? eligibleTitle : "Your Significant layer is empty"}
        </h2>
        <p className="mx-auto mt-2 max-w-sm text-sm leading-relaxed text-muted-foreground">
          {hasSignificantEntities
            ? eligibleDescription
            : "Build a focused case view by adding entities from the full graph, a selection, or Spotlight."}
        </p>
        <Button
          variant="outline"
          size="sm"
          className="mt-5"
          onClick={() => setLayer(caseId, "all")}
        >
          <ArrowLeft className="size-3.5" />
          Explore all case data
        </Button>
      </div>
    </div>
  )
}
