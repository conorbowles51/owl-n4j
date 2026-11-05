import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react"
import { keepPreviousData, useInfiniteQuery, useQuery } from "@tanstack/react-query"
import { Link, useParams, useSearchParams } from "react-router-dom"
import { ArrowLeft, ChevronLeft, ChevronRight, Search } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ProgressPanel } from "@/components/ui/progress-panel"
import { useProgressClock } from "@/components/ui/use-progress-clock"
import { useProtectedObjectUrl } from "@/lib/protected-file"
import { cn } from "@/lib/cn"
import { AddToMenu } from "@/features/phones/ui/AddToMenu"
import { liveCollectClient, undoCollect, type CollectResult, type CollectTarget } from "@/features/phones/collect.api"
import { useCollectTargets } from "@/features/phones/collect-targets"
import { evidenceAPI } from "../api"
import { markedPieces, type TextMark } from "../lib/text-marks"
import { selectionOffsets } from "../lib/text-selection"
import {
  QUOTE_MAX_CHARACTERS,
  textWorkbenchAPI,
  windowOffset,
  type PageRect,
  type PassageLocation,
  type TextPage,
  type TextPages,
  type TextReader,
} from "../text-workbench.api"

const n = (value: number) => value.toLocaleString("en-US")
const IMAGE_FILE = /\.(jpe?g|png|gif|bmp|webp)$/i
const MATCH_PAGE = 200

function ReaderLine({ reader, readAt }: { reader: TextReader; readAt?: string | null }) {
  return (
    <p className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground" data-testid="text-reader">
      <Badge variant={reader.machine_read ? "warning" : "slate"}>{reader.machine_read ? "Machine reading" : "Stored text"}</Badge>
      <span>{reader.words}</span>
      {reader.confidence != null && <span>OCR confidence {Math.round(reader.confidence)}%</span>}
      {reader.low_confidence && <span className="text-status-warning">Low confidence: check against the page</span>}
      {readAt && <span>Read {new Date(readAt).toLocaleDateString()}</span>}
    </p>
  )
}

/** How long each kind of wait took last time on this visit: the only time-left figure the panel may quote. */
const lastTook = new Map<string, number>()

/** The shared waiting panel (the page-speed standard): the step in words within 300 ms, Try again after 10 s. */
function Waiting({ kind, step, onRetry }: { kind: string; step: string; onRetry?: () => void }) {
  const [startedAt] = useState(() => performance.now())
  const now = useProgressClock(true, startedAt)
  useEffect(() => () => { lastTook.set(kind, performance.now() - startedAt) }, [kind, startedAt])
  return <ProgressPanel progress={{ step, startedAt, movedAt: startedAt, lastDurationMs: lastTook.get(kind) }} now={now} onRetry={onRetry} className="m-3" />
}

function Failed({ children, onRetry }: { children: ReactNode; onRetry: () => void }) {
  return (
    <div role="alert" className="flex items-center gap-3 p-4 text-sm text-destructive">
      {children}
      <Button size="sm" variant="outline" onClick={onRetry}>Retry</Button>
    </div>
  )
}

function PageImage(props: { evidenceId: string; page: number; rects: PageRect[]; name: string }) {
  const [attempt, setAttempt] = useState(0)
  return <PageImageAttempt key={`${props.page}:${attempt}`} {...props} onRetry={() => setAttempt((value) => value + 1)} />
}

function PageImageAttempt({ evidenceId, page, rects, name, onRetry }: { evidenceId: string; page: number; rects: PageRect[]; name: string; onRetry: () => void }) {
  const image = useProtectedObjectUrl(evidenceAPI.getPageImageUrl(evidenceId, page, 1200))
  if (image.error) return <Failed onRetry={onRetry}>Page {n(page)} could not be shown: {image.error.message}.</Failed>
  if (!image.objectUrl) return <Waiting kind="image" step={`Drawing page ${n(page)} from the original`} onRetry={onRetry} />
  return (
    <div className="relative">
      <img src={image.objectUrl} alt={`Page ${n(page)} of ${name}`} className="block w-full" />
      {rects.map((rect, index) => (
        <span key={index} data-testid="page-highlight" className="absolute bg-primary/30 ring-1 ring-primary"
          style={{ left: `${rect.x * 100}%`, top: `${rect.y * 100}%`, width: `${rect.width * 100}%`, height: `${rect.height * 100}%` }} />
      ))}
    </div>
  )
}

function WholeImage(props: { evidenceId: string; name: string }) {
  const [attempt, setAttempt] = useState(0)
  return <WholeImageAttempt key={attempt} {...props} onRetry={() => setAttempt((value) => value + 1)} />
}

function WholeImageAttempt({ evidenceId, name, onRetry }: { evidenceId: string; name: string; onRetry: () => void }) {
  const image = useProtectedObjectUrl(evidenceAPI.getFileUrl(evidenceId))
  if (image.error) return <Failed onRetry={onRetry}>The image could not be shown: {image.error.message}.</Failed>
  if (!image.objectUrl) return <Waiting kind="whole-image" step="Fetching the image" onRetry={onRetry} />
  return <img src={image.objectUrl} alt={name} className="block w-full" />
}

function Original({ data, evidenceId, page, rects, positionsNote }: {
  data: TextPages; evidenceId: string; page: number; rects: PageRect[]; positionsNote: string | null
}) {
  const shown = data.pages_in_step ? page : Math.min(page, data.image_pages)
  return (
    <section aria-label="Original" className="flex min-h-0 flex-col border-r border-border">
      <h2 className="border-b border-border px-3 py-2 text-xs font-semibold">
        Original{data.image_pages > 0 ? `, page ${n(shown)} of ${n(data.image_pages)}` : ""}
      </h2>
      {positionsNote && <p className="border-b border-border px-3 py-1 text-xs text-muted-foreground">{positionsNote}</p>}
      <div className="min-h-0 flex-1 overflow-auto bg-muted/30">
        {!data.original_available ? <p className="p-4 text-sm text-muted-foreground">The original file is not on the server, so only its text can be shown.</p>
          : data.image_pages > 0 ? <PageImage evidenceId={evidenceId} page={shown} rects={rects} name={data.document_name} />
            : IMAGE_FILE.test(data.document_name) ? <WholeImage evidenceId={evidenceId} name={data.document_name} />
              : <p className="p-4 text-sm text-muted-foreground">This kind of file has no page image. Open it from Evidence to see the original.</p>}
      </div>
    </section>
  )
}

function PageText({ page, marks, onSelect, textRef }: {
  page: TextPage; marks: TextMark[]; onSelect: () => void; textRef: React.RefObject<HTMLDivElement | null>
}) {
  const pieces = useMemo(() => markedPieces(page.text, marks), [page.text, marks])
  if (page.text_missing) return <p role="status" className="m-3 rounded border border-border bg-muted/30 p-3 text-sm" data-testid="text-missing">{page.text_missing}</p>
  return (
    <div ref={textRef} onMouseUp={onSelect} onKeyUp={onSelect} data-testid="page-text"
      className="whitespace-pre-wrap break-words p-3 font-mono text-xs leading-5 selection:bg-primary/25">
      {pieces.map((piece, index) => piece.kind === null ? <span key={index}>{piece.text}</span> : (
        <mark key={index} data-mark={piece.kind} className={cn("rounded-[2px] text-foreground",
          piece.kind === "current" ? "bg-primary/40 ring-1 ring-primary" : piece.kind === "passage" ? "bg-status-warning-soft ring-1 ring-status-warning" : "bg-primary/15")}>{piece.text}</mark>
      ))}
    </div>
  )
}

function KeptPassage({ passage }: { passage: PassageLocation }) {
  return (
    <div className="border-b border-border bg-muted/20 px-3 py-2 text-xs" data-testid="kept-passage">
      {passage.words && <p role="status" className="mb-1 font-medium">{passage.words}</p>}
      {passage.state !== "unchanged" && (
        <>
          <p className="whitespace-pre-wrap">Quote as taken{passage.taken_page ? ` from page ${n(passage.taken_page)}` : ""}: “{passage.quote}”</p>
          {passage.reader && <p className="text-muted-foreground">{passage.reader.words}</p>}
        </>
      )}
    </div>
  )
}

interface Picked { start: number; end: number; quote: string; page: TextPage }

function Selection({ caseId, data, picked, onClear }: { caseId: string; data: TextPages; picked: Picked; onClear: () => void }) {
  const targets = useCollectTargets(caseId)
  const length = picked.end - picked.start
  const tooLong = length > QUOTE_MAX_CHARACTERS
  const quote = picked.quote.replace(/\s+/g, " ").trim()
  const [undone, setUndone] = useState<string | null>(null)
  const undo = async (target: CollectTarget, result: CollectResult) => {
    try {
      await undoCollect(caseId, target, result)
      setUndone(`Removed the quote from ${target.label}.`)
    } catch (error) {
      setUndone(error instanceof Error ? error.message : "The quote could not be removed.")
    }
  }
  const links = useMemo(() => [{
    target_type: "evidence_passage" as const,
    target_id: `${data.evidence_id}:${(data.text_version ?? "").slice(0, 16)}:${picked.start}:${picked.end}`,
    label: quote.slice(0, 120),
    source_anchor: {},
  }], [data.evidence_id, data.text_version, picked.start, picked.end, quote])
  return (
    <div className="border-t border-border bg-card p-3" aria-label="Selected text" role="group">
      <p className="line-clamp-3 text-xs">“{quote}”</p>
      {picked.page.reader && <p className="mt-1 text-xs text-muted-foreground">Stays labelled: {picked.page.reader.words}.</p>}
      <div className="mt-2 flex flex-wrap items-start gap-2">
        {tooLong ? <p role="alert" className="text-xs text-destructive">A quote can be at most {n(QUOTE_MAX_CHARACTERS)} characters; this selection has {n(length)}. Select less.</p>
          : <AddToMenu caseId={caseId} links={links} noun="quotes" origin="Added from the text workbench" targets={targets.targets}
              client={liveCollectClient} keys={false} kinds={["finding", "note", "dossier"]} onUndo={(t, r) => void undo(t, r)}
              description="Each keeps a link back to this passage, and what read it." />}
        <Button size="sm" variant="ghost" onClick={onClear}>Clear selection</Button>
        {targets.note && <p className="text-xs text-muted-foreground">{targets.note}</p>}
        {undone && <p role="status" className="text-xs">{undone}</p>}
      </div>
    </div>
  )
}

export function TextWorkbenchPage() {
  const { id: caseId = "", fileId = "" } = useParams()
  const [params, setParams] = useSearchParams()
  const page = Math.max(1, Number(params.get("page")) || 1)
  const urlQuery = params.get("q") ?? ""
  const passageId = params.get("passage")
  const [draft, setDraft] = useState(urlQuery)
  const [matchIndex, setMatchIndex] = useState(0)
  const [picked, setPicked] = useState<Picked | null>(null)
  const textRef = useRef<HTMLDivElement | null>(null)

  const setPlace = useCallback((changes: Record<string, string | null>) => {
    setParams((current) => {
      const next = new URLSearchParams(current)
      for (const [key, value] of Object.entries(changes)) {
        if (value) next.set(key, value)
        else next.delete(key)
      }
      return next
    }, { replace: true })
  }, [setParams])
  const goToPage = useCallback((value: number) => { setPicked(null); setPlace({ page: String(value) }) }, [setPlace])

  const offset = windowOffset(page)
  const pages = useQuery({
    queryKey: ["text-workbench", "pages", fileId, offset],
    queryFn: ({ signal }) => textWorkbenchAPI.pages(fileId, offset, signal),
    enabled: !!fileId,
    staleTime: 60_000,
    placeholderData: keepPreviousData,
  })
  const data = pages.data
  const current = data?.pages.find((item) => item.page_number === page) ?? null

  const passage = useQuery({
    queryKey: ["text-workbench", "passage", fileId, passageId],
    queryFn: ({ signal }) => textWorkbenchAPI.passage(fileId, passageId as string, signal),
    enabled: !!passageId,
    staleTime: 60_000,
  })
  const passageData = passage.data
  const passagePage = passageData ? passageData.page_number ?? passageData.taken_page : null
  useEffect(() => {
    if (passagePage && passagePage !== Number(params.get("page"))) setPlace({ page: String(passagePage) })
    // the quote's place is applied once, when it arrives; a person may then turn the page
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [passagePage])

  const search = useInfiniteQuery({
    queryKey: ["text-workbench", "matches", fileId, urlQuery],
    queryFn: ({ pageParam, signal }) => evidenceAPI.getTextMatches(fileId, urlQuery, MATCH_PAGE, pageParam, signal),
    initialPageParam: 0,
    getNextPageParam: (last) => (last.has_more ? last.offset + last.returned_matches : undefined),
    enabled: urlQuery.length >= 2 && !!fileId,
  })
  const matches = useMemo(() => search.data?.pages.flatMap((item) => item.matches) ?? [], [search.data])
  const total = search.data?.pages[0]?.total_matches ?? 0

  const openMatch = useCallback(async (index: number) => {
    const match = matches[index]
    if (!match) return
    setMatchIndex(index)
    const target = match.page_number ?? (await textWorkbenchAPI.pageAt(fileId, match.start_char)).page_number
    if (target) goToPage(target)
  }, [fileId, goToPage, matches])
  // the next part of a long list of matches arrives before the person reaches its end
  const { fetchNextPage, hasNextPage, isFetchingNextPage } = search
  useEffect(() => {
    if (hasNextPage && !isFetchingNextPage && matchIndex >= matches.length - 2) void fetchNextPage()
  }, [fetchNextPage, hasNextPage, isFetchingNextPage, matchIndex, matches.length])
  const stepMatch = (step: 1 | -1) => void openMatch(Math.min((matchIndex + step + total) % total, matches.length - 1))
  const firstOpened = useRef("")
  useEffect(() => {
    const key = `${fileId}:${urlQuery}`
    if (!matches.length || firstOpened.current === key) return
    firstOpened.current = key
    // a hit opened with its page stays on it; only a page with no match moves to the first match
    const here = matches.findIndex((match) => match.page_number === page)
    if (here >= 0) setMatchIndex(here)
    else void openMatch(0)
  }, [fileId, matches, openMatch, page, urlQuery])

  const marks = useMemo<TextMark[]>(() => {
    if (!current || current.start_char == null || current.end_char == null) return []
    const start = current.start_char
    const end = current.end_char
    const out: TextMark[] = []
    matches.forEach((match, index) => {
      if (match.start_char >= start && match.end_char <= end) {
        out.push({ start: match.start_char - start, end: match.end_char - start, kind: index === matchIndex ? "current" : "match" })
      }
    })
    if (passageData?.start_char != null && passageData.end_char != null) {
      out.unshift({ start: passageData.start_char - start, end: passageData.end_char - start, kind: "passage" })
    }
    return out
  }, [current, matchIndex, matches, passageData])

  const showing = urlQuery || (passageData?.quote ?? "")
  const positionWords = showing.slice(0, 512)
  const canPosition = !!data && data.image_pages > 0 && data.pages_in_step && positionWords.trim().length >= 2
  const positions = useQuery({
    queryKey: ["text-workbench", "positions", fileId, page, positionWords],
    queryFn: ({ signal }) => textWorkbenchAPI.positions(fileId, page, positionWords, signal),
    enabled: canPosition,
    staleTime: 60_000,
  })
  const positionsNote = canPosition && positions.data && !positions.data.available
    ? "This page has no text layer, so the words cannot be marked on the image."
    : null

  const onSelect = useCallback(() => {
    const container = textRef.current
    if (!container || !current || current.start_char == null) return
    const selection = window.getSelection()
    const offsets = selectionOffsets(container, selection)
    if (!offsets || !selection) return
    setPicked({ start: current.start_char + offsets.start, end: current.start_char + offsets.end,
      quote: selection.toString(), page: current })
  }, [current])

  const back = `/cases/${encodeURIComponent(caseId)}/evidence`
  return (
    <div className="flex h-full min-h-0 flex-col" data-testid="text-workbench">
      <header className="flex flex-wrap items-center gap-2 border-b border-border px-3 py-2">
        <Button asChild size="sm" variant="ghost"><Link to={back}><ArrowLeft className="size-4" />Evidence</Link></Button>
        <h1 className="min-w-0 flex-1 truncate text-sm font-semibold">{data?.document_name ?? "Document"}</h1>
        {data && data.page_count > 0 && (
          <span className="flex items-center gap-1 text-xs">
            <Button size="icon-sm" variant="outline" aria-label="Previous page" disabled={page <= 1} onClick={() => goToPage(page - 1)}><ChevronLeft className="size-4" /></Button>
            <label className="flex items-center gap-1">
              Page
              <Input key={page} aria-label="Page number" defaultValue={page} inputMode="numeric" className="h-7 w-16 text-center text-xs"
                onKeyDown={(event) => {
                  if (event.key !== "Enter") return
                  const value = Number(event.currentTarget.value)
                  if (Number.isInteger(value) && value >= 1 && value <= data.page_count) goToPage(value)
                }} />
              of {n(data.page_count)}
            </label>
            <Button size="icon-sm" variant="outline" aria-label="Next page" disabled={page >= data.page_count} onClick={() => goToPage(page + 1)}><ChevronRight className="size-4" /></Button>
          </span>
        )}
        <form className="flex items-center gap-1" role="search" aria-label="Find in this document"
          onSubmit={(event) => { event.preventDefault(); setMatchIndex(0); firstOpened.current = ""; setPlace({ q: draft.trim() || null }) }}>
          <Input aria-label="Find in this document" placeholder="Find in this document" value={draft} onChange={(event) => setDraft(event.target.value)} className="h-7 w-52 text-xs" />
          <Button type="submit" size="icon-sm" variant="outline" aria-label="Find"><Search className="size-4" /></Button>
        </form>
        {urlQuery.length >= 2 && (
          <span className="flex items-center gap-1 text-xs" aria-live="polite">
            {search.isLoading ? null : search.isError ? <>The search failed.<Button size="sm" variant="outline" onClick={() => void search.refetch()}>Retry</Button></> : total === 0 ? "No matches in this text." : <>
              Match {n(matchIndex + 1)} of {n(total)}
              <Button size="icon-sm" variant="ghost" aria-label="Previous match" onClick={() => stepMatch(-1)}><ChevronLeft className="size-4" /></Button>
              <Button size="icon-sm" variant="ghost" aria-label="Next match" onClick={() => stepMatch(1)}><ChevronRight className="size-4" /></Button>
            </>}
          </span>
        )}
      </header>
      {urlQuery.length >= 2 && search.isLoading && <Waiting key={urlQuery} kind="find" step={`Finding "${urlQuery}" in this document`} onRetry={() => void search.refetch()} />}
      {pages.isLoading && <Waiting kind="document" step="Reading the document's pages" onRetry={() => void pages.refetch()} />}
      {pages.isError && <Failed onRetry={() => void pages.refetch()}>The document could not be loaded: {pages.error instanceof Error ? pages.error.message : "the request failed"}.</Failed>}
      {data && (
        <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-2">
          <Original data={data} evidenceId={fileId} page={page} rects={positions.data?.rects ?? []} positionsNote={positionsNote} />
          <section aria-label="Extracted text" className="flex min-h-0 flex-col">
            <div className="space-y-1 border-b border-border px-3 py-2">
              <h2 className="text-xs font-semibold">Extracted text{current ? `, ${current.label}` : ""}</h2>
              {current?.reader && <ReaderLine reader={current.reader} readAt={data.read_at} />}
              {!data.pages_in_step && <p className="text-xs text-muted-foreground">The stored text of this file is not divided by page, so the two sides do not keep step.</p>}
            </div>
            {passageData && <KeptPassage passage={passageData} />}
            {passage.isError && <p role="alert" className="border-b border-border px-3 py-2 text-xs text-destructive">That quote could not be found in this case.</p>}
            <div className="min-h-0 flex-1 overflow-auto">
              {data.text_absent && <p role="status" className="m-3 rounded border border-border bg-muted/30 p-3 text-sm" data-testid="text-absent">{data.text_absent}</p>}
              {!data.text_absent && current && <PageText page={current} marks={marks} onSelect={onSelect} textRef={textRef} />}
              {!data.text_absent && !current && !pages.isPlaceholderData && <p className="m-3 text-sm text-muted-foreground">Page {n(page)} is past the end of this document ({n(data.page_count)} pages).</p>}
              {!data.text_absent && !current && pages.isPlaceholderData && <Waiting key={page} kind="text" step={`Reading the text of page ${n(page)}`} onRetry={() => void pages.refetch()} />}
            </div>
            {picked && <Selection key={`${picked.start}:${picked.end}`} caseId={caseId} data={data} picked={picked} onClear={() => { setPicked(null); window.getSelection()?.removeAllRanges() }} />}
          </section>
        </div>
      )}
    </div>
  )
}
