import { useQuery } from "@tanstack/react-query"
import { Link, useParams, useSearchParams } from "react-router-dom"
import { failureText } from "@/features/phones/api"
import { searchGroup, type SearchHit } from "../api"
import { hitPath } from "../lib/open-hit"
import { GROUP_NAMES } from "../lib/search-words"
import { HitLine } from "./SearchDialog"

/**
 * Every hit of one search group (03 section 11.4), read 200 at a time until the group's total is reached, in the
 * group's reproducible order. The count read so far is shown against the total while it reads.
 */
export function SearchResultsPage() {
  const { id: caseId = "" } = useParams()
  const [params] = useSearchParams()
  const q = params.get("q") ?? ""
  const group = params.get("group") ?? "documents"
  const exact = params.get("exact") === "1"
  const res = useQuery({
    queryKey: ["case-search-group", caseId, q, group, exact],
    enabled: !!caseId && !!q,
    retry: false,
    queryFn: async ({ signal }) => {
      const items: SearchHit[] = []
      let cursor: string | null = null
      let total = 0
      let note: string | undefined
      let limits: string[] = []
      do {
        const page = await searchGroup(caseId, q, group, cursor, exact, signal)
        items.push(...page.items)
        total = page.total
        note = page.note
        limits = page.limits.map((l) => l.message)
        cursor = page.next_cursor
      } while (cursor)
      return { items, total, note, limits }
    },
  })
  const name = GROUP_NAMES[group] ?? group
  return (
    <div className="flex h-full flex-col gap-2 overflow-auto p-4">
      <h1 className="text-lg font-semibold">
        {name} matching {q}
      </h1>
      {res.isLoading && <p role="status" className="text-sm">Reading every match</p>}
      {res.isError && <p role="alert" className="text-sm">{failureText(res.error, "The search could not be run.")}</p>}
      {res.data && (
        <>
          <p role="status" className="text-sm">
            {res.data.total.toLocaleString("en-US")} {res.data.total === 1 ? "match" : "matches"}
            {exact ? ", exact characters" : ""}
          </p>
          {res.data.limits.map((m) => (
            <p key={m} role="alert" className="text-xs">
              {m}
            </p>
          ))}
          {res.data.note && <p className="text-xs">{res.data.note}</p>}
          <ul className="flex flex-col divide-y rounded border">
            {res.data.items.map((h, i) => (
              <li key={`${i}-${h.record_uid ?? h.evidence_file_id ?? h.identity_key ?? h.title}`} className="p-2">
                <Link to={hitPath(caseId, h)} className="block hover:bg-muted">
                  <HitLine hit={h} />
                </Link>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}

export default SearchResultsPage
