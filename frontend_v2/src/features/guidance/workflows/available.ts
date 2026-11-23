import { CATALOGUE } from "./catalogue"
import { TUTORIALS } from "./tutorials"
import type { TutorialStep, Workflow, WorkflowSwitch } from "./types"

export type SwitchState = Record<WorkflowSwitch, boolean>

/**
 * The steps a person sees: a step behind a switch that is off in their browser is left out, as tours do, and so is a
 * step for the version a switch that is on replaces.
 */
export function stepsShown(steps: TutorialStep[], switches: SwitchState): TutorialStep[] {
  return steps.filter((s) => (!s.switch || switches[s.switch]) && (!s.unless || !switches[s.unless]))
}

/** Every workflow with its steps; one whose every step waits behind a switch that is off is not listed. */
export function workflowsShown(switches: SwitchState): Workflow[] {
  return CATALOGUE.map((w) => ({ ...w, steps: stepsShown(TUTORIALS[w.id] ?? [], switches) })).filter((w) => w.steps.length > 0)
}

const IMG = `${import.meta.env.BASE_URL}docs/workflows/img/`

/** A step's picture: the phone-width crop on narrow screens, the desktop one otherwise. */
export function stepImage(shot: string, width: 1440 | 390) {
  return `${IMG}${shot}-${width}.webp`
}
