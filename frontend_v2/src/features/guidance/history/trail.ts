import type { Step } from "../api"

/** A run of steps as a theory group: each step keeps its address and view state, so it reopens from the theory. */
export function trailGroup(steps: Step[]) {
  const ordered = [...steps].sort((a, b) => a.at.localeCompare(b.at))
  return {
    group_type: "step_trail" as const,
    members: ordered.map((s) => ({ type: "history_step" as const, id: s.id, label: s.name })),
    how: { steps: ordered.map(({ id, name, screen, path, state, item, at }) => ({ id, name, screen, path, state, item, at })) },
    words: ordered.length === 1 ? ordered[0].name : `${ordered.length} steps, from ${ordered[0].name} to ${ordered[ordered.length - 1].name}`,
  }
}
