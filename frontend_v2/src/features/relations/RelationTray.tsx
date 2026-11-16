import { useEffect, useState } from "react"
import { Link, useParams } from "react-router-dom"
import { currentQuery, setCurrentQuery } from "./api"

/** The look in progress, which follows the investigator from screen to screen (lx-overlaps D). */
export function RelationTray() {
  const { id: caseId } = useParams()
  const [, bump] = useState(0)
  useEffect(() => {
    const on = () => bump((n) => n + 1)
    window.addEventListener("loupe-relation-query", on)
    window.addEventListener("storage", on)
    return () => {
      window.removeEventListener("loupe-relation-query", on)
      window.removeEventListener("storage", on)
    }
  }, [])
  const current = caseId ? currentQuery(caseId) : null
  if (!caseId || !current) return null
  return (
    <div role="status" className="fixed bottom-3 right-3 z-40 flex max-w-[calc(100vw-1.5rem)] flex-wrap items-center gap-x-3 gap-y-1 rounded-md border bg-background px-3 py-2 text-sm shadow-md">
      <span>Looking into how {current.count} items relate</span>
      <Link className="underline" to={`/cases/${caseId}/relations/${current.id}`}>Open</Link>
      <button type="button" className="text-muted-foreground underline" onClick={() => setCurrentQuery(caseId, null)}>Finish this look</button>
    </div>
  )
}
