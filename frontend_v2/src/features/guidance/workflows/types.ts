import type { TourArea } from "../tours"

/** A switch that keeps unreleased work off for a browser (lib/ui-switches.ts, features/phones/lib/phone-layers.ts). */
export type WorkflowSwitch = "corroborate-v2" | "phone_layers"

/** The questions a person brings to the case: the first way the list is grouped. */
export type QuestionId = "start" | "money" | "contact" | "there" | "when" | "who" | "theory" | "check" | "report"

/** Kinds of case: the second way the list is grouped. */
export type CaseKind = "any" | "fraud" | "drugs" | "harm" | "defence"

export interface TutorialStep {
  /** What to do, as a short heading: "Search for the cash deposits". */
  title: string
  /** The instruction in plain words: where to click and what to type. */
  body: string
  /** What the person should see on the demo case, with the true numbers, so they can tell they are on track. */
  expect: string
  /** The picture: public/docs/workflows/img/<shot>-1440.webp and -390.webp, taken by journeys/workflow-stills.mjs. */
  shot: string
  /** The picture's alt text: what it shows. */
  alt: string
  /**
   * "Open this screen": the address inside the person's case (after /cases/<id>/) and the control to ring there.
   * `then` is what the person does on that screen before the control shows (it sits inside something they open first,
   * such as one theory); the step bar says it until the control is ringed.
   */
  open: { to: string; target?: string[]; then?: string }
  /** Hidden while this switch is off in the person's browser. */
  switch?: WorkflowSwitch
}

/** One line of the catalogue (catalogue.ts): what the list shows and groups by. The steps are in tutorials/. */
export interface WorkflowEntry {
  id: string
  title: string
  /** One line: "Use this when ...". */
  useWhen: string
  questions: QuestionId[]
  kinds: CaseKind[]
  /** The areas of the app it passes through, in order; the first one's guide links to it. */
  areas: TourArea[]
  /** Ids from the guidance feature list (feature-list.ts) of the features this workflow's steps show. */
  features: string[]
  /** The assistant's guided workflow of the same name (backend services/agent/workflows.py), when there is one. */
  assistant?: string
  /** The switches any of its steps sits behind (each off unless turned on in the browser); the test checks the steps. */
  switches: WorkflowSwitch[]
}

export interface Workflow extends WorkflowEntry {
  steps: TutorialStep[]
}
