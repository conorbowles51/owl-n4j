import { lazy, Suspense, useEffect, useState } from "react"
import { OPEN_WORKFLOW, type OpenWorkflowDetail } from "./open"

// the list and the tutorials load only when the section is opened, so the case shell carries none of them
const WorkflowGuide = lazy(() => import("./WorkflowGuide"))

export interface WorkflowPlace {
  id?: string
  step: number
}

/**
 * The Workflows section of the Guide (lx-workflowguide C), mounted once per case beside the tour. It opens on
 * OPEN_WORKFLOW (the Guide menu, an area guide's link, Start here, a next step) at the list or at a workflow's step.
 * "Open this screen" closes the dialog and leaves a ring on the control and a way back to the same step.
 */
export function WorkflowHost({ caseId }: { caseId: string }) {
  const [state, setState] = useState<{ open: boolean; place: WorkflowPlace } | null>(null)
  useEffect(() => {
    const onOpen = (e: Event) => {
      const d = ((e as CustomEvent<OpenWorkflowDetail>).detail ?? {}) as OpenWorkflowDetail
      setState({ open: true, place: { id: d.id, step: d.step ?? 0 } })
    }
    window.addEventListener(OPEN_WORKFLOW, onOpen)
    return () => window.removeEventListener(OPEN_WORKFLOW, onOpen)
  }, [])
  if (!state) return null
  return (
    <Suspense fallback={null}>
      <WorkflowGuide
        caseId={caseId}
        open={state.open}
        place={state.place}
        onPlace={(place) => setState({ open: true, place })}
        onClose={() => setState(null)}
        onLeave={(place) => setState({ open: false, place })}
      />
    </Suspense>
  )
}
