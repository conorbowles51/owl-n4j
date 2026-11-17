import { lazy, Suspense } from "react"
import { Tray as RelationTray } from "@/features/relations/Tray"
import { useSwitch } from "@/lib/ui-switches"

// The selection tray, its question menu and the item keys load only when the switch is on, so they stay out of the
// main script (the size budget in frontend_v2/scripts/bundle-budget.js).
const CorroborateTray = lazy(() => import("./CorroborateTray").then((m) => ({ default: m.CorroborateTray })))
const ItemKeys = lazy(() => import("./ItemKeys").then((m) => ({ default: m.ItemKeys })))

/** Behind the switch `corroborate-v2` (off until Neil approves the page): the selection tray, else the look tray. */
export function TraySwitch() {
  const on = useSwitch("corroborate-v2")
  if (!on) return <RelationTray />
  return (
    <Suspense fallback={null}>
      <CorroborateTray />
      <ItemKeys />
    </Suspense>
  )
}
