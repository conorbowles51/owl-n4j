import { useState, type ReactNode } from "react"
import { Button } from "@/components/ui/button"

export function CaseworkHistory({ title, children }: { title: string; children: ReactNode[] }) {
  const [page, setPage] = useState(0)
  const pages = Math.max(1, Math.ceil(children.length / 3))
  const current = Math.min(page, pages - 1)
  return (
    <details className="border-t border-border pt-3">
      <summary className="cursor-pointer text-xs font-semibold">
        {title} <span className="ml-1 font-normal text-muted-foreground">({children.length})</span>
      </summary>
      <div className="mt-2 divide-y divide-border">
        {children.slice(current * 3, current * 3 + 3)}
      </div>
      {children.length === 0 ? <p className="py-2 text-xs text-muted-foreground">No history yet.</p> : null}
      {pages > 1 ? (
        <div className="mt-2 flex items-center justify-between text-xs text-muted-foreground">
          <Button variant="ghost" size="sm" disabled={current === 0} onClick={() => setPage(current - 1)}>Previous</Button>
          <span>Page {current + 1} of {pages}</span>
          <Button variant="ghost" size="sm" disabled={current === pages - 1} onClick={() => setPage(current + 1)}>Next</Button>
        </div>
      ) : null}
    </details>
  )
}
