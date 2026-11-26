import { useEffect, useState } from "react"
import { useParams, useSearchParams } from "react-router-dom"
import { openCorroborate } from "@/features/leads/open"
import { corroborateAPI } from "./api"

/**
 * Opens a question the assistant drafted (lx-corrorest F). The link `?corro_draft=<id>` puts the draft's items in the
 * selection and opens the Corroborate page with the drafted question chosen (lx-corroredo A). Nothing runs: the person
 * presses Ask.
 */
export function DraftOpener() {
  const { id: caseId } = useParams()
  const [params, setParams] = useSearchParams()
  const draft = params.get("corro_draft")
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    if (!caseId || !draft) return
    let live = true
    corroborateAPI.draft(caseId, draft)
      .then((d) => {
        if (!live) return
        const people = Array.isArray(d.question.chips?.people) ? (d.question.chips.people as string[]) : undefined
        openCorroborate({ caseId, screen: "the assistant", label: `Drafted by the assistant: ${d.question.text ?? "a question"} (${d.members.length.toLocaleString("en-US")})`,
                          members: d.members, kind: d.question.kind, drafted: true, ...(people ? { people } : {}) })
      })
      .catch((e) => live && setError(e instanceof Error ? e.message : "The drafted question could not be opened."))
    return () => { live = false }
  }, [caseId, draft])
  const close = () => {
    setError(null)
    const next = new URLSearchParams(params)
    next.delete("corro_draft")
    setParams(next, { replace: true })
  }
  if (!caseId || !draft || !error) return null
  return <p role="alert" className="fixed bottom-2 left-2 z-50 rounded border bg-background p-2 text-xs">{error} <button className="underline" onClick={close}>Close</button></p>
}
