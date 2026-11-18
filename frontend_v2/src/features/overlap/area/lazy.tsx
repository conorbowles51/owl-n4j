import { lazy, Suspense } from "react"
import { useSwitch } from "@/lib/ui-switches"
import { useAreaCompare } from "./store"

const AreaCompare = lazy(() => import("./AreaCompare"))

/** The comparison panel over the Map, loaded only when opened. */
export function LazyAreaCompare({ caseId, areas }: { caseId: string; areas: number[][][] }) {
  const on = useSwitch("corroborate-v2")
  const open = useAreaCompare((s) => s.open)
  if (!on || !open || areas.length === 0) return null
  return (
    <Suspense fallback={<p role="status" className="absolute right-3 top-14 z-20 rounded bg-card px-2 py-1 text-xs shadow">Opening the comparison…</p>}>
      <AreaCompare caseId={caseId} areas={areas} />
    </Suspense>
  )
}
