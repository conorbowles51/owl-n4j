import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query"
import { useCallback, useEffect, useMemo, useState } from "react"
import { Link, useNavigate, useSearchParams } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { ApiError } from "@/lib/api-client"
import { failureText, getRecordList, type RecordListFilter } from "../api"
import { liveCollectClient, type CollectLink } from "../collect.api"
import { PhoneRecordPanel } from "../components/RecordPanel"
import { useCollectTargets } from "../hooks/use-collect"
import { phonesQuery } from "../phones-query"
import type { RecordListRow } from "../schemas"
import { AddToMenu } from "../ui/AddToMenu"
import { PhoneTable, type Column, type ServerSort } from "../ui/PhoneTable"
import { fmt } from "../ui/count-sentence"
import { usePhoneSelection } from "@/stores/phone-selection.store"
import { recordListFilter } from "./record-list-url"

/**
 * The list for one record type (03 section 7.5): columns from the type's mapping or field names, the exact total, the
 * record panel for any row and Add to…. The server sorts and pages: the browser holds only the windows it scrolled to.
 * A message or call opens in Conversations, where it is read among its thread; any other row opens the record panel.
 */

const LEVEL_WORDS: Record<string, string> = {
  reviewed: "Interpreted",
  applied_unconfirmed: "Not yet confirmed",
  generic: "Read generically",
  captured_only: "Held, not yet read",
}
const PLACEMENT_WORDS = { all: "All records", top: "Standing on their own", nested: "Inside other records" } as const

function Cell({ cell }: { cell?: RecordListRow["cells"][string] }) {
  if (!cell) return <span className="text-muted-foreground">—</span>
  return (
    <span title={cell.original ? `Original: ${cell.original}` : cell.text}>
      {cell.masked ? <span aria-label="Hidden sensitive value">{cell.text}</span> : cell.text}
      {cell.more > 0 && <span className="text-muted-foreground"> +{fmt(cell.more)}</span>}
      {cell.original && <span className="text-xs text-muted-foreground"> (corrected, was {cell.original})</span>}
    </span>
  )
}

export function RecordListPage({ caseId, extraction, modelType }: { caseId: string; extraction: string; modelType: string }) {
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const selection = usePhoneSelection()
  const phones = useQuery(phonesQuery(caseId))
  const targets = useCollectTargets(caseId)
  const [panel, setPanel] = useState<string | null>(null)
  const [restarted, setRestarted] = useState(false)
  const chosen = recordListFilter(`?${params}`)
  const wholeCase = params.get("phone") === "all"
  const filter: RecordListFilter = useMemo(
    () => ({ ...chosen, phones: wholeCase ? [] : [extraction] }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [params, extraction],
  )
  const queryKey = useMemo(() => ["phone-record-list", caseId, modelType, filter] as const, [caseId, modelType, filter])
  const list = useInfiniteQuery({
    queryKey,
    queryFn: ({ pageParam }) => getRecordList(caseId, modelType, filter, pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next,
    enabled: !!caseId && !!modelType,
    retry: false,
  })
  const stale = list.error instanceof ApiError && list.error.status === 409
  // the phone was read again while this list was open: a later window would not continue the earlier ones
  useEffect(() => {
    if (!stale) return
    setRestarted(true)
    void queryClient.resetQueries({ queryKey })
  }, [stale, queryClient, queryKey])
  useEffect(() => selection.setCase(caseId), [selection, caseId])

  const pages = list.data?.pages
  const rows = useMemo(() => (pages ?? []).flatMap((p) => p.items), [pages])
  const first = pages?.[0]
  const total = first?.total ?? 0
  const { hasNextPage, isFetchingNextPage, fetchNextPage } = list
  const more = useCallback(() => {
    if (hasNextPage && !isFetchingNextPage) void fetchNextPage()
  }, [hasNextPage, isFetchingNextPage, fetchNextPage])

  const set = (name: string, value: string | null) =>
    setParams((p) => {
      const next = new URLSearchParams(p)
      if (value) next.set(name, value)
      else next.delete(name)
      return next
    }, { replace: true })

  const open = useCallback(
    (row: RecordListRow) => {
      if (row.open_in === "conversations")
        navigate(`/cases/${encodeURIComponent(caseId)}/phones/${encodeURIComponent(row.extraction_id)}/records/conversations?record=${encodeURIComponent(row.record_uid)}`)
      else setPanel(row.record_uid)
    },
    [caseId, navigate],
  )
  const labels = useMemo(() => Object.fromEntries((phones.data?.phones ?? []).map((p) => [p.extraction_id, p.label])), [phones.data])
  const columns = useMemo<Column<RecordListRow>[]>(
    () => [
      {
        id: "record",
        header: "Record",
        width: 260,
        serverKey: "title",
        cell: (r) => (
          <button type="button" className="underline underline-offset-2" onClick={(e) => { e.stopPropagation(); open(r) }}>
            {r.title || modelType}
          </button>
        ),
      },
      { id: "time", header: "Time", width: 210, serverKey: "time", cell: (r) => r.time ?? <span className="text-muted-foreground">No time</span> },
      ...(wholeCase ? [{ id: "phone", header: "Phone", width: 120, cell: (r: RecordListRow) => labels[r.extraction_id] ?? "" }] : []),
      ...(first?.columns ?? []).map((c) => ({ id: `f:${c.id}`, header: c.header, width: 180, cell: (r: RecordListRow) => <Cell cell={r.cells[c.id]} /> })),
      { id: "state", header: "State", width: 110, serverKey: "deleted", cell: (r) => r.deleted_state ?? "Not stated" },
      {
        id: "mark",
        header: "Reading",
        width: 240,
        cell: (r) => (
          <span>
            {r.copy ? "Copy from another source" : LEVEL_WORDS[r.interpretation_level ?? ""] ?? r.interpretation_level ?? ""}
            {r.owner && (
              <>
                {" · in "}
                <button type="button" className="underline underline-offset-2" onClick={(e) => { e.stopPropagation(); setPanel(r.owner!.record_uid) }}>
                  {r.owner.model_type}
                </button>
              </>
            )}
          </span>
        ),
      },
    ],
    [first?.columns, labels, modelType, open, wholeCase],
  )
  const sort: ServerSort = {
    sort: { key: filter.sort ?? "time", dir: filter.direction === "desc" ? "descending" : "ascending" },
    onChange: (s) => setParams((p) => {
      const next = new URLSearchParams(p)
      next.set("sort", s.key)
      next.set("direction", s.dir === "descending" ? "desc" : "asc")
      return next
    }, { replace: true }),
  }
  const links: CollectLink[] = useMemo(() => {
    const byId = new Map(rows.map((r) => [r.record_uid, r]))
    return selection.ids.flatMap((id) => {
      const r = byId.get(id)
      return r ? [{ target_type: "phone_record", target_id: id, label: r.title || modelType, source_anchor: { extraction_id: r.extraction_id, record_type: modelType } }] : []
    })
  }, [rows, selection.ids, modelType])
  const summary = `/cases/${encodeURIComponent(caseId)}/phones/${encodeURIComponent(extraction)}`

  return (
    <div className="flex h-full min-h-0 flex-col gap-2 p-4">
      <header className="flex flex-wrap items-baseline gap-3">
        <h1 className="text-lg font-semibold">{modelType}</h1>
        <Link className="text-sm underline underline-offset-2" to={summary}>
          Phone summary
        </Link>
        <span className="ml-auto">
          <AddToMenu caseId={caseId} links={links} noun="records" targets={targets.data ?? []} client={liveCollectClient} origin={`Added from the ${modelType} list`} />
        </span>
      </header>
      <form aria-label="Filter the list" className="flex flex-wrap items-end gap-3 text-xs" onSubmit={(e) => e.preventDefault()}>
        <label className="flex flex-col gap-0.5">
          <span className="font-medium">Phones</span>
          <select className="h-8 rounded border bg-background px-1 text-sm" value={wholeCase ? "all" : "this"} onChange={(e) => set("phone", e.target.value === "all" ? "all" : null)}>
            <option value="this">This phone</option>
            <option value="all">Every phone in the case</option>
          </select>
        </label>
        <label className="flex flex-col gap-0.5">
          <span className="font-medium">Where in the report</span>
          <select className="h-8 rounded border bg-background px-1 text-sm" value={filter.placement ?? "all"} onChange={(e) => set("placement", e.target.value === "all" ? null : e.target.value)}>
            {Object.entries(PLACEMENT_WORDS).map(([k, w]) => <option key={k} value={k}>{w}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-0.5">
          <span className="font-medium">Deleted</span>
          <select className="h-8 rounded border bg-background px-1 text-sm" value={filter.deleted ?? "any"} onChange={(e) => set("deleted", e.target.value === "any" ? null : e.target.value)}>
            <option value="any">Deleted and not deleted</option>
            <option value="only">Deleted or in trash only</option>
            <option value="hide">Leave out deleted</option>
          </select>
        </label>
        <label className="flex flex-col gap-0.5">
          <span className="font-medium">Copies from another source</span>
          <select className="h-8 rounded border bg-background px-1 text-sm" value={filter.copies ?? "any"} onChange={(e) => set("copies", e.target.value === "any" ? null : e.target.value)}>
            <option value="any">Shown, marked</option>
            <option value="only">Copies only</option>
            <option value="hide">Leave out copies</option>
          </select>
        </label>
        <label className="flex flex-col gap-0.5">
          <span className="font-medium">From</span>
          <input type="date" className="h-8 rounded border bg-background px-1 text-sm" value={filter.from ?? ""} onChange={(e) => set("from", e.target.value || null)} />
        </label>
        <label className="flex flex-col gap-0.5">
          <span className="font-medium">To</span>
          <input type="date" className="h-8 rounded border bg-background px-1 text-sm" value={filter.to ?? ""} onChange={(e) => set("to", e.target.value || null)} />
        </label>
      </form>
      {list.isLoading && <p role="status" className="text-sm">Loading the list</p>}
      {list.isError && !stale && (
        <div role="alert" className="text-sm">
          <p>{failureText(list.error, "The list could not be loaded.")}</p>
          <Button size="sm" variant="outline" className="mt-2" onClick={() => void list.refetch()}>Try again</Button>
        </div>
      )}
      {restarted && <p role="status" className="text-xs">This phone was read again while the list was open, so the list started again from the top.</p>}
      {first && total === 0 && <p className="text-sm">No {modelType} records match these filters.</p>}
      <div className="flex min-h-0 flex-1 gap-2">
      {first && total > 0 && (
        <div className="flex min-w-0 flex-1 flex-col gap-2">
          <PhoneTable
            rows={rows}
            total={total}
            columns={columns}
            rowId={(r) => r.record_uid}
            noun={`${modelType} records`}
            singular={`${modelType} record`}
            label={`${modelType} records`}
            height={Math.max(320, window.innerHeight - 300)}
            onOpen={open}
            serverSort={sort}
            onNearEnd={more}
          />
          <p className="text-xs text-muted-foreground">
            Times in {first.zone}.
            {first.no_time > 0 && ` ${fmt(first.no_time)} ${first.no_time === 1 ? "record has" : "records have"} no time and ${first.no_time === 1 ? "is" : "are"} not in this date range.`}
            {first.more_fields > 0 && ` ${fmt(first.more_fields)} more ${first.more_fields === 1 ? "field is" : "fields are"} in each record.`}
          </p>
        </div>
      )}
      <PhoneRecordPanel title="The record" caseId={caseId} recordUid={panel} zone={first?.zone} onClose={() => setPanel(null)} />
      </div>
    </div>
  )
}
