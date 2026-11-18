import { Button } from "@/components/ui/button"
import { useSwitch } from "@/lib/ui-switches"
import { useAreaCompare } from "./store"

/** Opens the area comparison for the drawn areas (behind corroborate-v2). */
export function CompareAreasButton({ count }: { count: number }) {
  const on = useSwitch("corroborate-v2")
  const show = useAreaCompare((s) => s.show)
  if (!on || count === 0) return null
  return (
    <Button size="sm" variant="outline" className="w-full" onClick={show} data-testid="compare-areas">
      {count === 1 ? "Look into this area over time" : `Compare these ${count} areas over time`}
    </Button>
  )
}
