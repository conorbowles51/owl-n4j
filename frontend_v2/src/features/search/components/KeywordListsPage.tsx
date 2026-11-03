import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { Link, useParams, useSearchParams } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { failureText } from "@/features/phones/api"
import { fetchAPI } from "@/lib/api-client"
import { attachKeywordList, listKeywordLists, type KeywordList } from "../api"
import { hitsPath } from "../lib/keyword-list-path"

/**
 * Saved keyword lists (03 section 11.2; 07 J-6 "Saves"): each list's terms, when it last ran and on how many phones,
 * every phone it could not count in full, and the exact total per phone, term and group. A total opens every hit for
 * that phone and term, and each hit opens the record in context, as a search does. A list can be attached to a
 * theory (07 section 14).
 */
export function KeywordListsPage() {
  const { id: caseId = "" } = useParams()
  const [params] = useSearchParams()
  const focus = params.get("list")
  const res = useQuery({
    queryKey: ["keyword-lists", caseId],
    queryFn: () => listKeywordLists(caseId),
    enabled: !!caseId,
    // a list just saved, or one whose phones changed, runs in the phone worker within a minute
    refetchInterval: (q) => (q.state.data?.items.some((i) => i.state !== "current") ? 15_000 : false),
  })
  return (
    <div className="flex h-full flex-col gap-3 overflow-auto p-4">
      <h1 className="text-lg font-semibold">Keyword lists</h1>
      <p className="text-sm text-muted-foreground">
        Each list runs on every phone in the case, including phones added later, and again whenever a phone is read or
        re-read. Save a list from search (Ctrl+K), with &ldquo;Save as keyword list&rdquo;.
      </p>
      {res.isLoading && <p role="status" className="text-sm">Reading the keyword lists</p>}
      {res.isError && <p role="alert" className="text-sm">{failureText(res.error, "The keyword lists could not be read.")}</p>}
      {res.data && res.data.total === 0 && <p className="text-sm">No keyword list is saved in this case yet.</p>}
      {res.data && res.data.total > 0 && (
        <p className="text-xs text-muted-foreground">
          {res.data.total.toLocaleString("en-US")} {res.data.total === 1 ? "list" : "lists"}
        </p>
      )}
      {res.data?.items.map((l) => <KeywordListCard key={l.entry_id} caseId={caseId} list={l} open={!focus || focus === l.entry_id} />)}
    </div>
  )
}

function KeywordListCard({ caseId, list, open }: { caseId: string; list: KeywordList; open: boolean }) {
  const run = list.run
  return (
    <section className="rounded border p-3" data-testid="keyword-list" aria-label={`Keyword list ${list.name}`}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-medium">{list.name}</h2>
        <span className="text-xs text-muted-foreground">
          {list.terms.length} {list.terms.length === 1 ? "term" : "terms"}
          {list.exact ? ", exact characters" : ""}
          {list.created_by ? `, saved by ${list.created_by}` : ""}
        </span>
      </div>
      <p className="text-sm" data-testid="keyword-list-summary" role={list.state === "current" ? undefined : "status"}>
        {list.summary}
      </p>
      {run?.not_counted.map((p) => (
        <p key={p.extraction_id} role="alert" className="text-xs">
          {p.message}
        </p>
      ))}
      <TheoryLine caseId={caseId} list={list} />
      {open && run && (
        <div className="mt-2 overflow-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-muted-foreground">
                <th className="p-1">Term</th>
                <th className="p-1">All phones</th>
                {run.phones.map((p) => (
                  <th key={p.extraction_id} className="p-1">
                    {p.phone_label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {list.terms.map((t) => (
                <tr key={t} className="border-t align-top">
                  <td className="p-1 font-medium">{t}</td>
                  <td className="p-1">{(run.terms[t] ?? 0).toLocaleString("en-US")}</td>
                  {run.phones.map((p) => (
                    <td key={p.extraction_id} className="p-1">
                      <PhoneCell caseId={caseId} list={list} term={t} phone={p} />
                    </td>
                  ))}
                </tr>
              ))}
              <tr className="border-t text-xs">
                <td className="p-1">Total</td>
                <td className="p-1">{run.total.toLocaleString("en-US")}</td>
                {run.phones.map((p) => (
                  <td key={p.extraction_id} className="p-1">
                    {p.total.toLocaleString("en-US")}
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

function PhoneCell({ caseId, list, term, phone }: { caseId: string; list: KeywordList; term: string; phone: NonNullable<KeywordList["run"]>["phones"][number] }) {
  const groups = phone.terms[term] ?? {}
  const words = list.run?.group_words ?? {}
  const shown = Object.entries(groups).filter(([, n]) => n > 0)
  if (!shown.length) return <span className="text-muted-foreground">0</span>
  return (
    <ul className="flex flex-col">
      {shown.map(([g, n]) => (
        <li key={g}>
          <Link className="underline" to={hitsPath(caseId, term, g, phone.extraction_id, list.exact)}>
            {n.toLocaleString("en-US")} {words[g] ?? g}
          </Link>
        </li>
      ))}
    </ul>
  )
}

type TheoryOption = { id: string; title: string | null }

function TheoryLine({ caseId, list }: { caseId: string; list: KeywordList }) {
  const qc = useQueryClient()
  const [picking, setPicking] = useState(false)
  const [chosen, setChosen] = useState("")
  const theories = useQuery({
    queryKey: ["keyword-list-theories", caseId],
    enabled: picking,
    queryFn: async () => {
      const r = await fetchAPI<{ entries: TheoryOption[]; total: number }>(
        `/api/workspace/${encodeURIComponent(caseId)}/entries?entry_type=theory&limit=200&sort_by=title&sort_direction=asc`,
      )
      return r
    },
  })
  const attach = useMutation({
    mutationFn: (theoryId: string) => attachKeywordList(caseId, list.entry_id, theoryId),
    onSuccess: () => {
      setPicking(false)
      setChosen("")
      void qc.invalidateQueries({ queryKey: ["keyword-lists", caseId] })
    },
  })
  return (
    <div className="mt-1 flex flex-wrap items-center gap-2 text-xs">
      {list.theories.length ? (
        <span>
          Attached to {list.theories.length === 1 ? "theory" : "theories"}: {list.theories.map((t) => t.title || "Untitled theory").join(", ")}
        </span>
      ) : (
        <span className="text-muted-foreground">Not attached to a theory.</span>
      )}
      {!picking ? (
        <Button size="sm" variant="outline" onClick={() => setPicking(true)}>
          Attach to a theory
        </Button>
      ) : (
        <>
          <select aria-label="Theory" className="rounded border px-1 py-0.5" value={chosen} onChange={(e) => setChosen(e.target.value)}>
            <option value="">{theories.isLoading ? "Reading theories" : "Choose a theory"}</option>
            {(theories.data?.entries ?? []).map((t) => (
              <option key={t.id} value={t.id}>
                {t.title || "Untitled theory"}
              </option>
            ))}
          </select>
          <Button size="sm" disabled={!chosen || attach.isPending} onClick={() => attach.mutate(chosen)}>
            Attach
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setPicking(false)}>
            Cancel
          </Button>
          {theories.data && theories.data.total === 0 && <span>This case has no theory yet.</span>}
          {theories.data && theories.data.total > theories.data.entries.length && (
            <span role="status">
              Showing the first {theories.data.entries.length} of {theories.data.total.toLocaleString("en-US")} theories by title.
            </span>
          )}
        </>
      )}
      {attach.isError && <span role="alert">{failureText(attach.error, "The list could not be attached.")}</span>}
    </div>
  )
}

/** A theory's keyword lists and their current totals (07 section 14), shown on the theory. */
export function TheoryKeywordLists({ caseId, theoryId }: { caseId: string; theoryId: string }) {
  const res = useQuery({ queryKey: ["keyword-lists", caseId, "theory", theoryId], queryFn: () => listKeywordLists(caseId, theoryId) })
  if (!res.data || res.data.total === 0) return null
  return (
    <section className="space-y-1 rounded-lg border border-border p-3" data-testid="theory-keyword-lists">
      <h3 className="text-sm font-semibold">Keyword lists</h3>
      {res.data.items.map((l) => (
        <p key={l.entry_id} className="text-sm">
          <Link className="underline" to={`/cases/${encodeURIComponent(caseId)}/keyword-lists?list=${encodeURIComponent(l.entry_id)}`}>
            {l.name}
          </Link>
          : {l.terms.join(", ")}. {l.summary}
        </p>
      ))}
    </section>
  )
}

export default KeywordListsPage
