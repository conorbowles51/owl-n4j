import { ArrowLeft, Star } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useCaseLayer, useCaseLayerStore } from "../stores/case-layer.store"
import { useSignificantManifest } from "../hooks/use-significant"

export function SignificantLayerBar({ caseId }: { caseId: string }) {
  const layer = useCaseLayer(caseId)
  const setLayer = useCaseLayerStore((state) => state.setLayer)
  const { data } = useSignificantManifest(caseId)

  if (layer !== "significant") return null

  return (
    <div className="relative flex h-9 shrink-0 items-center gap-2 overflow-hidden border-b border-amber-500/25 bg-amber-500/[0.075] px-3 text-amber-950 dark:text-amber-100">
      <div className="absolute inset-y-0 left-0 w-0.5 bg-amber-500" />
      <Star className="size-3.5 fill-amber-500 text-amber-500" />
      <span className="text-xs font-semibold">Significant layer</span>
      <span className="font-mono text-[10px] tabular-nums text-amber-800/70 dark:text-amber-200/70">
        {(data?.count ?? 0).toLocaleString()} entities
      </span>
      <span className="hidden text-[10px] text-amber-800/60 dark:text-amber-200/60 xl:inline">
        Live references to the underlying case data · significance does not imply verification
      </span>
      <Button
        variant="ghost"
        size="sm"
        className="ml-auto h-6 px-2 text-[10px] text-amber-900 hover:bg-amber-500/15 dark:text-amber-100"
        onClick={() => setLayer(caseId, "all")}
      >
        <ArrowLeft className="size-3" />
        All data
      </Button>
    </div>
  )
}
