import type { AgentSteeringEntry } from "./types"

/** One line of the investigation trail. */
export interface InvestigationTrailStep {
  id: string
  toolName?: string | null
  title: string
  detail?: string | null
  result?: string | null
  status: "running" | "success" | "error"
  durationMs?: number | null
  /** A switch or note from the person, shown as its own trail line. */
  steering?: AgentSteeringEntry
}

/** Tool steps and the person's switches and notes in one list, newest first: an entry the run took after step N sits
 * after the Nth tool step; an entry not yet taken is the newest. */
export function trailNewestFirst(
  toolSteps: InvestigationTrailStep[],
  steering: AgentSteeringEntry[],
): InvestigationTrailStep[] {
  const ordered: InvestigationTrailStep[] = []
  const taken = steering.filter((entry) => entry.step != null).sort((a, b) => (a.step ?? 0) - (b.step ?? 0))
  const pending = steering.filter((entry) => entry.step == null)
  let next = 0
  toolSteps.forEach((step, index) => {
    while (next < taken.length && (taken[next].step ?? 0) <= index) {
      ordered.push(steeringStep(taken[next]))
      next += 1
    }
    ordered.push(step)
  })
  taken.slice(next).forEach((entry) => ordered.push(steeringStep(entry)))
  pending.forEach((entry) => ordered.push(steeringStep(entry)))
  return ordered.reverse()
}

function steeringStep(entry: AgentSteeringEntry): InvestigationTrailStep {
  return { id: `steer_${entry.id}`, title: entry.title, result: entry.result, status: "success", steering: entry }
}
