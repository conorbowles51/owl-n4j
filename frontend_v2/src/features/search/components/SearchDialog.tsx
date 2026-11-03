import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useEffect, useMemo, useRef, useState } from "react"
import { useLocation, useNavigate } from "react-router-dom"
import { Command, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { failureText } from "@/features/phones/api"
import { saveKeywordList, searchCase, splitTerms, type SearchGroup, type SearchHit } from "../api"
import { GROUP_KINDS, GROUP_NAMES, rememberQuery, recentQueries } from "../lib/search-words"
import { conversationsWithText, hitPath } from "../lib/open-hit"

/**
 * Loupe-wide search (03 section 11.4): Cmd/Ctrl+K anywhere in a case. Every group shows its exact total and its
 * first hits; Enter opens the highlighted hit, and the highlight starts on the top hit of the group whose top hit
 * scores highest. A group's full list opens in Conversations (messages, calls, emails) or on the results page.
 */
export function SearchDialog({ caseId }: { caseId: string }) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState("")
  const [typed, setTyped] = useState("")
  const [exact, setExact] = useState(false)
  const [value, setValue] = useState("")
  const navigate = useNavigate()
  const location = useLocation()
  const listRef = useRef<HTMLDivElement>(null)
  const restoreScroll = useRef<number | null>(null)
  const handledKey = useRef<string | null>(null)

  // Back to the page a hit was opened from reopens the results where they were (S-9).
  useEffect(() => {
    const saved = (location.state as { caseSearch?: { q: string; exact: boolean; scroll: number } } | null)?.caseSearch
    if (!saved || handledKey.current === location.key) return
    handledKey.current = location.key
    setTyped(saved.q)
    setQ(saved.q)
    setExact(saved.exact)
    restoreScroll.current = saved.scroll
    setOpen(true)
  }, [location.key, location.state])

  const inputRef = useRef<HTMLInputElement>(null)
  useEffect(() => {
    // Ctrl+K opens search; pressed again while it is open, it selects the words typed so a new search can start
    // (Escape closes). Closing on the second press lost the box under the person's hands (07 J-6).
    const toggle = () => {
      if (!open) return setOpen(true)
      inputRef.current?.focus()
      inputRef.current?.select()
    }
    document.addEventListener("owl:toggle-command-palette", toggle)
    return () => document.removeEventListener("owl:toggle-command-palette", toggle)
  }, [open])
  useEffect(() => {
    const t = window.setTimeout(() => setQ(typed.trim()), 250)
    return () => window.clearTimeout(t)
  }, [typed])

  const res = useQuery({
    queryKey: ["case-search", caseId, q, exact],
    queryFn: ({ signal }) => searchCase(caseId, q, exact, signal),
    enabled: open && q.length > 0,
    placeholderData: keepPreviousData,
    staleTime: 15_000,
    retry: false,
  })
  const data = res.data && res.data.query === q ? res.data : undefined
  const shown = useMemo(() => (data ? data.groups.filter((g) => g.total > 0) : []), [data])
  const empty = data ? data.groups.filter((g) => g.total === 0).map((g) => GROUP_NAMES[g.group] ?? g.group) : []

  // Enter rule: start on the top hit of the group whose top hit scores highest.
  useEffect(() => {
    if (!shown.length) return
    const best = [...shown].sort((a, b) => (b.score ?? 0) - (a.score ?? 0))[0]
    if (!best.items[0]) return
    // after cmdk's own pass, which highlights the first item once new items mount
    const t = window.setTimeout(() => setValue(itemValue(best, best.items[0], 0)), 0)
    return () => window.clearTimeout(t)
  }, [shown])

  const go = (path: string) => {
    rememberQuery(q)
    // this entry remembers the search, so Back to it shows the same results at the same place (S-9)
    navigate(`${location.pathname}${location.search}${location.hash}`, {
      replace: true,
      state: { ...((location.state as object | null) ?? {}), caseSearch: { q, exact, scroll: listRef.current?.scrollTop ?? 0 } },
    })
    handledKey.current = null
    setOpen(false)
    navigate(path)
  }

  useEffect(() => {
    if (restoreScroll.current === null || !shown.length || !listRef.current) return
    listRef.current.scrollTop = restoreScroll.current
    restoreScroll.current = null
  }, [shown])

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="overflow-hidden p-0 sm:max-w-2xl">
        <DialogHeader className="sr-only">
          <DialogTitle>Search this case</DialogTitle>
          <DialogDescription>Search messages, calls, emails, people, phone records and documents</DialogDescription>
        </DialogHeader>
        <Command shouldFilter={false} value={value} onValueChange={setValue} className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:text-muted-foreground [&_[cmdk-item]]:px-2 [&_[cmdk-item]]:py-2">
          <CommandInput ref={inputRef} placeholder="Search words, names, numbers or accounts" value={typed} onValueChange={setTyped} aria-label="Search this case" />
          <div className="flex items-center gap-3 border-b px-3 py-1.5 text-xs">
            <label className="flex items-center gap-1.5">
              <input type="checkbox" checked={exact} onChange={(e) => setExact(e.target.checked)} />
              Exact characters
            </label>
            {res.isFetching && <span role="status">Searching</span>}
          </div>
          <CommandList ref={listRef} className="max-h-[60vh]">
            <SearchBody
              q={q}
              typed={typed}
              data={data}
              shown={shown}
              empty={empty}
              error={res.isError ? failureText(res.error, "The search could not be run.") : null}
              setTyped={setTyped}
              onOpen={(hit) => go(hitPath(caseId, hit))}
              onAll={(g) =>
                go(
                  GROUP_KINDS[g.group]
                    ? conversationsWithText(caseId, q, GROUP_KINDS[g.group], exact)
                    : `/cases/${encodeURIComponent(caseId)}/search?${new URLSearchParams({ q, group: g.group, ...(exact ? { exact: "1" } : {}) })}`,
                )
              }
            />
          </CommandList>
        </Command>
        {/* outside the command list, so typing and Enter here never move or open a hit */}
        <SaveKeywordList caseId={caseId} q={q} exact={exact} onOpenLists={() => go(`/cases/${encodeURIComponent(caseId)}/keyword-lists`)} />
      </DialogContent>
    </Dialog>
  )
}

const itemValue = (g: SearchGroup, h: SearchHit, i: number) => `${g.group}:${i}:${h.record_uid ?? h.evidence_file_id ?? h.identity_key ?? h.title}`

function SearchBody(props: {
  q: string
  typed: string
  data: Awaited<ReturnType<typeof searchCase>> | undefined
  shown: SearchGroup[]
  empty: string[]
  error: string | null
  setTyped: (v: string) => void
  onOpen: (hit: SearchHit) => void
  onAll: (g: SearchGroup) => void
}) {
  const { q, typed, data, shown, empty, error } = props
  if (!typed.trim()) {
    const recent = recentQueries()
    return recent.length ? (
      <CommandGroup heading="Recent searches in this tab">
        {recent.map((r) => (
          <CommandItem key={r} value={`recent:${r}`} onSelect={() => props.setTyped(r)}>
            {r}
          </CommandItem>
        ))}
      </CommandGroup>
    ) : (
      <p className="p-4 text-sm text-muted-foreground">Type a word, name, number or account. Letters written in fancy styles are found by their plain letters.</p>
    )
  }
  if (error) return <p role="alert" className="p-4 text-sm">{error}</p>
  if (!data) return <p className="p-4 text-sm text-muted-foreground">Searching for {q || typed.trim()}</p>
  return (
    <>
      {data.short && (
        <div className="px-4 pt-3 text-xs">
          <p>{data.short}</p>
          <p className="text-muted-foreground">Shorter text is matched against numbers and identifiers only.</p>
        </div>
      )}
      {data.limits.map((l) => (
        <p key={l.message} role="alert" className="px-4 pt-3 text-xs">
          {l.message}
        </p>
      ))}
      {shown.length === 0 && <p className="p-4 text-sm">Nothing in this case matches {data.query}.</p>}
      {shown.map((g) => (
        <CommandGroup key={g.group} heading={`${GROUP_NAMES[g.group] ?? g.group} (${g.total.toLocaleString("en-US")})`}>
          {g.note && <p className="px-2 pb-1 text-xs">{g.note}</p>}
          {g.items.map((h, i) => (
            <CommandItem key={itemValue(g, h, i)} value={itemValue(g, h, i)} onSelect={() => props.onOpen(h)}>
              <HitLine hit={h} />
            </CommandItem>
          ))}
          {g.total > g.items.length && (
            <CommandItem value={`all:${g.group}`} onSelect={() => props.onAll(g)}>
              {GROUP_KINDS[g.group] ? `Show all ${g.total.toLocaleString("en-US")} in Conversations` : `Show all ${g.total.toLocaleString("en-US")}`}
            </CommandItem>
          )}
        </CommandGroup>
      ))}
      <div className="border-t px-4 py-2 text-xs text-muted-foreground">
        {empty.length > 0 && <p>No matches in: {empty.join(", ")}.</p>}
        {data.not_searched.map((n) => (
          <p key={n.group}>{n.reason}</p>
        ))}
      </div>
    </>
  )
}

export function HitLine({ hit }: { hit: SearchHit }) {
  const s = hit.snippet
  return (
    <span className="flex min-w-0 flex-col gap-0.5">
      <span className="truncate text-xs text-muted-foreground">
        {[hit.title, hit.time, hit.page ? `page ${hit.page}` : null].filter(Boolean).join(" · ")}
      </span>
      {s && (
        <span className="line-clamp-2 text-sm">
          {s.before}
          <mark className="rounded-sm bg-status-review-soft px-0.5">{s.match}</mark>
          {s.after}
        </span>
      )}
      {hit.original && (
        // a machine translation cites its original, which is what the evidence says (05 17.5)
        <span className="line-clamp-2 text-xs" data-testid="hit-original">
          Original{hit.translated_from ? ` (${hit.translated_from})` : ""}: {hit.original.text}
          {hit.original.clipped ? ` … (${hit.original.chars.toLocaleString("en-US")} characters in all)` : ""}
        </span>
      )}
      {hit.origin?.words ? (
        <span className="text-xs italic text-muted-foreground">{hit.origin.words}</span>
      ) : hit.machine_generated && hit.label ? (
        <span className="text-xs italic text-muted-foreground">{hit.label}</span>
      ) : null}
    </span>
  )
}

/**
 * Save the search as a keyword list (03 section 11.2; 07 J-6 "Saves"): a name and its terms, one per line, the
 * search's words first. The list runs on every phone in the case, including phones added later.
 */
export function SaveKeywordList({ caseId, q, exact, onOpenLists }: { caseId: string; q: string; exact: boolean; onOpenLists: () => void }) {
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const [name, setName] = useState("")
  const [terms, setTerms] = useState("")
  const save = useMutation({
    mutationFn: () => saveKeywordList(caseId, name.trim(), splitTerms(terms), exact),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["keyword-lists", caseId] }),
  })
  const start = () => {
    setName(q)
    setTerms(q)
    save.reset()
    setOpen(true)
  }
  return (
    <div className="border-t px-3 py-2 text-xs">
      {!open ? (
        <div className="flex flex-wrap items-center gap-3">
          <button type="button" className="underline disabled:no-underline disabled:opacity-60" disabled={!q} onClick={start}>
            Save as keyword list
          </button>
          <button type="button" className="underline" onClick={onOpenLists}>
            Keyword lists
          </button>
        </div>
      ) : save.isSuccess ? (
        <p role="status">
          Saved &ldquo;{save.data.name}&rdquo; with {save.data.terms.length} {save.data.terms.length === 1 ? "term" : "terms"}. It runs on every phone in
          the case within a minute, and again when a phone is added or read again.{" "}
          <button type="button" className="underline" onClick={onOpenLists}>
            Open keyword lists
          </button>
        </p>
      ) : (
        <form
          className="flex flex-col gap-1.5"
          onSubmit={(e) => {
            e.preventDefault()
            save.mutate()
          }}
        >
          <label className="flex flex-col gap-0.5">
            Name
            <input className="rounded border px-1.5 py-1 text-sm" value={name} maxLength={240} onChange={(e) => setName(e.target.value)} aria-label="Keyword list name" />
          </label>
          <label className="flex flex-col gap-0.5">
            Terms, one per line
            <textarea className="rounded border px-1.5 py-1 text-sm" rows={3} value={terms} onChange={(e) => setTerms(e.target.value)} aria-label="Keyword list terms" />
          </label>
          {exact && <p>The terms match exact characters, as this search does.</p>}
          {save.isError && <p role="alert">{failureText(save.error, "The keyword list could not be saved.")}</p>}
          <div className="flex gap-2">
            <button type="submit" className="rounded border px-2 py-1" disabled={save.isPending || !name.trim() || !splitTerms(terms).length}>
              {save.isPending ? "Saving" : "Save list"}
            </button>
            <button type="button" className="px-2 py-1" onClick={() => setOpen(false)}>
              Cancel
            </button>
          </div>
        </form>
      )}
    </div>
  )
}
