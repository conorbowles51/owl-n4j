import { useState } from "react"
import { Button } from "@/components/ui/button"
import { useSwitch } from "@/lib/ui-switches"
import { corroborateAPI } from "./api"
import { QuestionMenu } from "./QuestionMenu"
import { addPart } from "./selection-store"

/**
 * "Corroborate this area" (lx-corroselect C): every phone position, photo and place inside the drawn areas joins the
 * selection, each tested on its own position. The count is stated before the menu opens.
 */
export function CorroborateArea({ caseId, areas }: { caseId: string; areas: number[][][] }) {
  const on = useSwitch("corroborate-v2")
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<string | null>(null)
  const [menu, setMenu] = useState(false)
  if (!on || areas.length === 0) return null
  const go = async () => {
    setBusy(true)
    setNote(null)
    try {
      const got = await corroborateAPI.area(caseId, areas)
      if (got.total === 0) {
        setNote("Nothing is inside the drawn area: no phone positions, photos or places.")
        return
      }
      const kinds = Object.entries(got.by_kind).map(([k, n]) => `${n.toLocaleString("en-US")} ${k}`)
      addPart(caseId, {
        screen: "the map",
        label: `${areas.length === 1 ? "Area" : `${areas.length} areas`}: ${[...kinds, got.places ? `${got.places} places` : ""].filter(Boolean).join(", ")} from ${got.phones} phones`,
        members: got.members,
        skipped: [],
      })
      setMenu(true)
    } catch (e) {
      setNote(e instanceof Error ? e.message : "The area could not be read.")
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="flex flex-col gap-1">
      <Button size="sm" variant="outline" disabled={busy} onClick={() => void go()}>
        {busy ? "Reading the area…" : "Corroborate this area"}
      </Button>
      {note && <p role="status" className="text-[10px] text-muted-foreground">{note}</p>}
      {menu && <QuestionMenu caseId={caseId} onClose={() => setMenu(false)} />}
    </div>
  )
}
