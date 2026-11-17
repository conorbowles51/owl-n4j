import { useEffect, useState } from "react"
import { useParams, useSearchParams } from "react-router-dom"
import { corroborateAPI } from "./api"
import { QuestionMenu } from "./QuestionMenu"
import { addPart } from "./selection-store"

/**
 * Opens a question the assistant drafted (lx-corrorest F). The link `?corro_draft=<id>` puts the draft's items in the
 * selection and opens the composer with the question chosen. Nothing runs: the person presses Corroborate.
 */
export function DraftOpener() {
  const { id: caseId } = useParams()
  const [params, setParams] = useSearchParams()
  const draft = params.get("corro_draft")
  const [open, setOpen] = useState<{ kind?: string } | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    if (!caseId || !draft) return
    let live = true
    corroborateAPI.draft(caseId, draft)
      .then((d) => {
        if (!live) return
        addPart(caseId, { screen: "the assistant", label: `Drafted by the assistant: ${d.question.text ?? "a question"} (${d.members.length.toLocaleString("en-US")})`, members: d.members, skipped: [] })
        setOpen({ kind: d.question.kind })
      })
      .catch((e) => live && setError(e instanceof Error ? e.message : "The drafted question could not be opened."))
    return () => { live = false }
  }, [caseId, draft])
  const close = () => {
    setOpen(null)
    setError(null)
    const next = new URLSearchParams(params)
    next.delete("corro_draft")
    setParams(next, { replace: true })
  }
  if (!caseId || !draft) return null
  if (error) return <p role="alert" className="fixed bottom-2 left-2 z-50 rounded border bg-background p-2 text-xs">{error} <button className="underline" onClick={close}>Close</button></p>
  return open ? <QuestionMenu caseId={caseId} draftedKind={open.kind} onClose={close} /> : null
}
