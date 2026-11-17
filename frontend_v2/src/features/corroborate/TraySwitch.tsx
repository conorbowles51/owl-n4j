import { Tray as RelationTray } from "@/features/relations/Tray"
import { useSwitch } from "@/lib/ui-switches"
import { CorroborateTray } from "./CorroborateTray"
import { ItemKeys } from "./ItemKeys"

/** Behind the switch `corroborate-v2` (off until Neil approves the page): the selection tray, else the look tray. */
export function TraySwitch() {
  return useSwitch("corroborate-v2") ? <><CorroborateTray /><ItemKeys /></> : <RelationTray />
}
