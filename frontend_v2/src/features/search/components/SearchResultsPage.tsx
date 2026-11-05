import { useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { Link, useParams, useSearchParams } from "react-router-dom"
import { useCase } from "@/features/cases/hooks/use-cases"
import { useCasePermissions } from "@/features/cases/hooks/use-case-permissions"
import { failureText } from "@/features/phones/api"
import { liveCollectClient, undoCollect, type CollectLink } from "@/features/phones/collect.api"
import { useCollectTargets } from "@/features/phones/hooks/use-collect"
import { AddToMenu } from "@/features/phones/ui/AddToMenu"
import { freezeSearchGroup, searchGroup, type SearchGroup, type SearchHit } from "../api"
import { dossierRefused, hitLink, noun, SELECTION_AS_ONE, SELECTION_GROUPS } from "../lib/hit-links"
import { hitPath } from "../lib/open-hit"
import { GROUP_NAMES } from "../lib/search-words"
import { HitLine, PaymentTotalsLine } from "./SearchDialog"

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
  // a keyword list's total opens the hits of one phone (03 section 11.2)
  const phones = (params.get("phones") ?? "").split(",").filter(Boolean)
  const res = useQuery({
    queryKey: ["case-search-group", caseId, q, group, exact, phones.join(",")],
    enabled: !!caseId && !!q,
    retry: false,
    queryFn: async ({ signal }) => {
      const items: SearchHit[] = []
      let cursor: string | null = null
      let total = 0
      let note: string | undefined
      let limits: string[] = []
      let totals: SearchGroup["totals"] = null
      let searched: string | undefined
      do {
        const page = await searchGroup(caseId, q, group, cursor, exact, signal, phones)
        items.push(...page.items)
        total = page.total
        note = page.note
        totals = totals ?? page.totals ?? null
        searched = page.searched
        limits = page.limits.map((l) => l.message)
        cursor = page.next_cursor
      } while (cursor)
      return { items, total, note, limits, totals, searched }
    },
  })
  const name = GROUP_NAMES[group] ?? group
  const caseQuery = useCase(caseId)
  const { canEdit } = useCasePermissions(caseQuery.data)
  const collect = useCollectTargets(caseId)
  const [picked, setPicked] = useState<ReadonlySet<number>>(new Set())
  const [all, setAll] = useState(false)
  const [undoNote, setUndoNote] = useState<string | null>(null)
  const items = res.data?.items
  const total = res.data?.total ?? 0
  const asOne = all && total > SELECTION_AS_ONE && SELECTION_GROUPS.has(group)
  // a whole group past 500 is kept as one frozen selection (07 6.1); asked only when "every hit" is chosen
  const frozen = useQuery({
    queryKey: ["search-group-selection", caseId, q, group, exact, phones.join(",")],
    queryFn: () => freezeSearchGroup(caseId, q, group, exact, phones),
    enabled: asOne && canEdit,
    retry: false,
    staleTime: Infinity,
  })
  const chosen: { links: CollectLink[]; none: number } = { links: [], none: 0 }
  ;(items ?? []).forEach((h, i) => {
    if (!all && !picked.has(i)) return
    const link = hitLink(h, q)
    if (link) chosen.links.push(link)
    else chosen.none += 1
  })
  const links: CollectLink[] = asOne
    ? frozen.data ? [{ target_type: "phone_selection", target_id: frozen.data.id, label: frozen.data.words, source_anchor: { origin: "search", query: q } }] : []
    : chosen.links
  const refused = dossierRefused(group)
  const targets = collect.data ?? []
  const notAllowed = !canEdit ? "A case member who can edit can add." : asOne && frozen.isError ? failureText(frozen.error, "The whole result could not be prepared for adding.") : undefined
  const addNoun = asOne ? "selection" : noun(group)
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
            {phones.length ? `, on ${phones.length === 1 ? "one phone" : `${phones.length} phones`}` : ""}
          </p>
          {res.data.limits.map((m) => (
            <p key={m} role="alert" className="text-xs">
              {m}
            </p>
          ))}
          {res.data.note && <p className="text-xs">{res.data.note}</p>}
          {res.data.totals && <PaymentTotalsLine totals={res.data.totals} />}
          {res.data.searched && <p className="text-xs text-muted-foreground">{res.data.searched}</p>}
          {res.data.items.length > 0 && (
            <div className="flex flex-wrap items-center gap-3 text-sm" aria-label="Add to">
              <label className="flex items-center gap-1.5">
                <input type="checkbox" checked={all} onChange={(e) => { setAll(e.target.checked); setPicked(new Set()) }} />
                Every hit ({total.toLocaleString("en-US")})
              </label>
              {!all && picked.size > 0 && <span role="status">{picked.size.toLocaleString("en-US")} chosen</span>}
              <AddToMenu
                caseId={caseId}
                links={links}
                noun={addNoun}
                targets={targets}
                client={liveCollectClient}
                origin="Added from Search"
                keys={false}
                disabledReason={notAllowed}
                noDossierWhy={refused ?? undefined}
                onUndo={(target, result) => {
                  setUndoNote("Undoing the add")
                  undoCollect(caseId, target, result)
                    .then((n) => setUndoNote(`Removed ${n.toLocaleString("en-US")} ${n === 1 ? "link" : "links"} that add made.`))
                    .catch((e) => setUndoNote(e instanceof Error ? e.message : "The add could not be undone."))
                }}
              />
            </div>
          )}
          {undoNote && <p role="status" className="text-xs">{undoNote}</p>}
          {!asOne && chosen.none > 0 && (
            <p role="note" className="text-xs">{chosen.none.toLocaleString("en-US")} of the hits chosen {chosen.none === 1 ? "has" : "have"} nothing that can be saved and will be left out.</p>
          )}
          {asOne && frozen.isLoading && <p role="status" className="text-xs">Preparing all {total.toLocaleString("en-US")} {noun(group)} to add as one selection</p>}
          {asOne && frozen.data && (
            <p role="status" className="text-xs">
              All {frozen.data.event_count.toLocaleString("en-US")} {noun(group)} ({frozen.data.record_count.toLocaleString("en-US")} records, every copy included) will be added as one selection.
              {frozen.data.left_out > 0 ? ` ${frozen.data.left_out.toLocaleString("en-US")} of the ${frozen.data.group_total.toLocaleString("en-US")} hits have no phone record behind them and are left out.` : ""}
            </p>
          )}
          <ul className="flex flex-col divide-y rounded border">
            {res.data.items.map((h, i) => (
              <li key={`${i}-${h.record_uid ?? h.evidence_file_id ?? h.identity_key ?? h.title}`} className="flex items-start gap-2 p-2">
                <input
                  type="checkbox"
                  className="mt-1"
                  aria-label={`Choose ${h.title}`}
                  disabled={all || !hitLink(h, q)}
                  checked={all || picked.has(i)}
                  onChange={(e) => setPicked((p) => {
                    const next = new Set(p)
                    if (e.target.checked) next.add(i)
                    else next.delete(i)
                    return next
                  })}
                />
                <Link to={hitPath(caseId, h)} className="block min-w-0 flex-1 hover:bg-muted">
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
