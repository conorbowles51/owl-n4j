import { Button } from "@/components/ui/button"
import { useSwitch } from "@/lib/ui-switches"
import type { RelationMember } from "@/features/relations/api"
import { openCorroborate } from "./open"

/** "Corroborate" on one thing (a dossier person, a phone, a graph line): opens the panel over the page. Behind the
 * switch corroborate-v2. */
export function CorroborateAction({ caseId, screen, label, members, people, size = "sm" }: {
  caseId: string
  screen: string
  label: string
  members: RelationMember[]
  people?: string[]
  size?: "sm" | "default"
}) {
  const on = useSwitch("corroborate-v2")
  if (!on) return null
  return (
    <Button size={size} variant="outline" disabled={!members.length}
      title="Corroborate this: the leads already here, or a new question"
      onClick={() => openCorroborate({ caseId, screen, label, members, people })}>
      Corroborate
    </Button>
  )
}
