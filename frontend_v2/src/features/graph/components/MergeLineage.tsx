import { useQuery } from "@tanstack/react-query"
import { graphAPI } from "../api"

/** What this entity was merged from: each merge that made it, with the names and keys it replaced. */
export function MergeLineage({ caseId, entityKey }: { caseId: string; entityKey: string }) {
  const query = useQuery({
    queryKey: ["graph", "merge-lineage", caseId, entityKey],
    queryFn: () => graphAPI.getMergeLineage(caseId, entityKey),
    enabled: !!caseId && !!entityKey,
  })
  if (query.isError)
    return (
      <p role="status" className="mx-4 my-2 text-xs text-muted-foreground">
        What this entity was merged from could not be read.
      </p>
    )
  const merges = query.data?.merges ?? []
  if (!merges.length) return null
  return (
    <section aria-label="Merged from" className="mx-4 my-3 rounded border p-3 text-xs">
      <h4 className="mb-1.5 font-semibold uppercase tracking-wider text-muted-foreground">Merged from</h4>
      <ul className="space-y-2">
        {merges.map((merge) => (
          <li key={merge.merge_job_id}>
            <p className="text-muted-foreground">
              {merge.at ? `On ${merge.at.slice(0, 10)}` : "In an earlier merge"}
              {merge.by ? `, ${merge.by} merged` : ", merged"}
              {merge.into === entityKey ? ":" : ` into ${merge.into}:`}
              {merge.status === "partial" && " (some sources could not be removed from the graph)"}
            </p>
            <ul className="mt-0.5 space-y-0.5 pl-3">
              {merge.sources.map((source) => (
                <li key={source.key} className="break-words">
                  <span className="font-medium">{source.name || "No name on record"}</span>{" "}
                  <span className="text-muted-foreground">({source.key})</span>
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
    </section>
  )
}
