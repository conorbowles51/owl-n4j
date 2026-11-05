import { Link } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { scopeHref } from "./scope"
import type { Scope } from "./ScopeBar"

type Screen = "conversations" | "map" | "timeline" | "graph" | "media" | "summary"

/** Crossings that carry the scope (07 4.5): the receiving screen shows the same chips and states what it cannot apply. */
export function ScopeCrossings({ caseId, scope, here }: { caseId: string; scope: Scope; here: Screen }) {
  const base = `/cases/${encodeURIComponent(caseId)}`
  const links: { to: Screen; words: string; href: string }[] = [
    { to: "conversations", words: "Conversations", href: scopeHref(`${base}/conversations`, scope) },
    { to: "timeline", words: "Show on Timeline", href: scopeHref(`${base}/timeline`, scope) },
    { to: "map", words: "Show on Map", href: scopeHref(`${base}/map`, scope) },
    { to: "graph", words: "Open in Graph", href: scopeHref(`${base}/graph`, scope, { scope: "phones" }) },
  ]
  return (
    <nav aria-label="Carry this scope" className="flex flex-wrap gap-1.5">
      {links.filter((l) => l.to !== here).map((l) => (
        <Button key={l.to} asChild size="sm" variant="outline">
          <Link to={l.href}>{l.words}</Link>
        </Button>
      ))}
    </nav>
  )
}
