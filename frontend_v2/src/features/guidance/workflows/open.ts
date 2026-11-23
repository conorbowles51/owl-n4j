/**
 * Opening the Workflows section of the Guide (lx-workflowguide C) from anywhere: the Guide menu, an area guide, Start
 * here, a next-step card. Kept apart from the catalogue so the case shell carries only this event, never the
 * tutorials, which load when the section opens.
 */
export const OPEN_WORKFLOW = "loupe:open-workflow"

export interface OpenWorkflowDetail {
  /** The workflow to open; none opens the list. */
  id?: string
  /** The step to open at, counted from 0. */
  step?: number
}

export function openWorkflow(detail: OpenWorkflowDetail = {}) {
  window.dispatchEvent(new CustomEvent<OpenWorkflowDetail>(OPEN_WORKFLOW, { detail }))
}

/** A link inside an area guide: `[Where did the money go?](#workflow=money)`. */
export const GUIDE_LINK = "#workflow="
