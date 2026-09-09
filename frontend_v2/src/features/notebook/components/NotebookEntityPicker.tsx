import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Loader2, Search } from "lucide-react"
import { Input } from "@/components/ui/input"
import { graphAPI } from "@/features/graph/api"
import type { GraphNode } from "@/types/graph.types"
import type { NotebookLinkInput } from "../api"

export function NotebookEntityPicker({
  caseId,
  onAttach,
}: {
  caseId: string
  onAttach: (link: NotebookLinkInput) => void
}) {
  const [query, setQuery] = useState("")
  const normalizedQuery = query.trim()
  const searchQuery = useQuery({
    queryKey: ["notebook", caseId, "entity-search", normalizedQuery],
    queryFn: () => graphAPI.search(normalizedQuery, caseId, 8),
    enabled: normalizedQuery.length >= 2,
    staleTime: 15_000,
  })

  const attach = (node: GraphNode) => {
    onAttach({
      target_type: "entity",
      target_id: node.key,
      target_label: node.label,
      metadata: { source: "entity_search" },
    })
    setQuery("")
  }

  return (
    <div className="space-y-2">
      <div className="relative">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input
          aria-label="Find an entity to link"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Find an entity to link"
          className="h-8 pl-8 text-xs"
        />
      </div>

      {normalizedQuery.length >= 2 ? (
        <div
          aria-live="polite"
          className="max-h-32 overflow-y-auto rounded-md border border-border bg-muted/20"
        >
          {searchQuery.isLoading ? (
            <div className="flex items-center gap-2 px-2 py-2 text-xs text-muted-foreground">
              <Loader2 className="size-3.5 animate-spin" />
              Searching
            </div>
          ) : searchQuery.isError ? (
            <p className="px-2 py-2 text-xs text-destructive">
              Entity search is unavailable. Try again.
            </p>
          ) : searchQuery.data?.nodes.length ? (
            searchQuery.data.nodes.map((node) => (
              <button
                key={node.key}
                type="button"
                className="flex w-full min-w-0 items-center justify-between gap-2 px-2 py-1.5 text-left text-xs transition-colors hover:bg-background focus-visible:bg-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                onClick={() => attach(node)}
              >
                <span className="min-w-0 truncate font-medium">{node.label}</span>
                <span className="shrink-0 text-[10px] text-muted-foreground">
                  {node.type}
                </span>
              </button>
            ))
          ) : (
            <p className="px-2 py-2 text-xs text-muted-foreground">
              No matching entities
            </p>
          )}
        </div>
      ) : null}
    </div>
  )
}
