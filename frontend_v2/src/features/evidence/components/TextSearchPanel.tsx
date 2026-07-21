import { useState } from "react"
import { useInfiniteQuery } from "@tanstack/react-query"
import {
  AlertCircle,
  ChevronDown,
  ChevronRight,
  FileImage,
  FileSpreadsheet,
  FileText,
  Film,
  FolderOpen,
  Loader2,
  Music,
  Search,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { DocumentViewer } from "@/components/ui/document-viewer"
import { cn } from "@/lib/cn"
import type {
  EvidenceTextSearchDocument,
  EvidenceTextSearchHit,
} from "@/types/evidence.types"
import { evidenceAPI } from "../api"
import { useEvidenceStore } from "../evidence.store"
import { useEvidenceTextSearch } from "../hooks/use-text-search"

interface ViewerTarget {
  evidenceId: string
  documentName: string
  page: number
  navigationKey: string
}

function HighlightedSnippet({ hit }: { hit: EvidenceTextSearchHit }) {
  const start = Math.max(0, Math.min(hit.highlight_start, hit.snippet.length))
  const end = Math.max(start, Math.min(hit.highlight_end, hit.snippet.length))

  return (
    <span className="break-words">
      {hit.snippet.slice(0, start)}
      <mark className="rounded-[2px] bg-primary/18 px-0.5 text-foreground ring-1 ring-primary/20">
        {hit.snippet.slice(start, end)}
      </mark>
      {hit.snippet.slice(end)}
    </span>
  )
}

function DocumentTypeIcon({ filename }: { filename: string }) {
  const extension = filename.split(".").pop()?.toLowerCase()
  if (["csv", "xls", "xlsx"].includes(extension ?? "")) return <FileSpreadsheet className="size-4" />
  if (["jpg", "jpeg", "png", "gif", "tif", "tiff", "webp"].includes(extension ?? "")) return <FileImage className="size-4" />
  if (["mp3", "wav", "m4a", "ogg", "flac"].includes(extension ?? "")) return <Music className="size-4" />
  if (["mp4", "mov", "avi", "mkv", "webm"].includes(extension ?? "")) return <Film className="size-4" />
  return <FileText className="size-4" />
}

function HitButton({
  hit,
  onOpen,
}: {
  hit: EvidenceTextSearchHit
  onOpen: () => void
}) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className="group w-full rounded-md border border-transparent px-2.5 py-2 text-left transition-colors hover:border-border hover:bg-muted/45 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <p className="text-xs leading-5 text-muted-foreground group-hover:text-foreground">
        <HighlightedSnippet hit={hit} />
      </p>
      {hit.location_label && (
        <span className="mt-1 inline-flex font-mono text-[10px] text-muted-foreground/75">
          {hit.location_label}
        </span>
      )}
    </button>
  )
}

function DocumentResultCard({
  document,
  query,
  onOpen,
}: {
  document: EvidenceTextSearchDocument
  query: string
  onOpen: (document: EvidenceTextSearchDocument, hit: EvidenceTextSearchHit) => void
}) {
  const [expanded, setExpanded] = useState(false)
  const matchesQuery = useInfiniteQuery({
    queryKey: ["evidence-text-matches", document.evidence_id, query],
    queryFn: ({ pageParam, signal }) =>
      evidenceAPI.getTextMatches(document.evidence_id, query, 50, pageParam, signal),
    initialPageParam: 0,
    getNextPageParam: (page) =>
      page.has_more ? page.offset + page.returned_matches : undefined,
    enabled: expanded,
  })
  const expandedMatches = matchesQuery.data?.pages.flatMap((page) => page.matches) ?? []
  const expandedTotal = matchesQuery.data?.pages[0]?.total_matches ?? document.total_matches
  const visibleMatches = expanded ? expandedMatches : document.matches
  const shownCount = expanded ? expandedMatches.length : document.shown_matches

  return (
    <article className="overflow-hidden rounded-lg border border-border bg-card shadow-xs">
      <div className="flex items-start gap-2.5 border-b border-border/70 p-3">
        <button
          type="button"
          onClick={() => document.matches[0] && onOpen(document, document.matches[0])}
          className="flex min-w-0 flex-1 items-start gap-2.5 rounded text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
            <DocumentTypeIcon filename={document.document_name} />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-semibold text-foreground">
              {document.document_name}
            </span>
            <span className="mt-0.5 flex items-center gap-1 truncate text-[11px] text-muted-foreground">
              <FolderOpen className="size-3 shrink-0" />
              {document.folder_path}
            </span>
          </span>
        </button>
        <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] font-medium tabular-nums text-muted-foreground">
          {document.total_matches}
        </span>
      </div>

      <div className="space-y-0.5 p-1.5">
        {expanded && matchesQuery.isLoading ? (
          <div className="flex items-center justify-center gap-2 py-8 text-xs text-muted-foreground">
            <Loader2 className="size-3.5 animate-spin" />
            Loading matches…
          </div>
        ) : expanded && matchesQuery.isError ? (
          <div className="flex items-center justify-between gap-3 p-2 text-xs text-destructive">
            <span>Couldn’t load all matches.</span>
            <Button size="sm" variant="outline" onClick={() => matchesQuery.refetch()}>
              Retry
            </Button>
          </div>
        ) : (
          visibleMatches.map((hit) => (
            <HitButton
              key={hit.id}
              hit={hit}
              onOpen={() => onOpen(document, hit)}
            />
          ))
        )}
      </div>

      <div className="flex min-h-9 items-center justify-between gap-2 border-t border-border/70 bg-muted/20 px-3 py-1.5">
        <span className="font-mono text-[10px] tabular-nums text-muted-foreground">
          Showing {shownCount} of {expandedTotal} matches
        </span>
        {document.total_matches > document.shown_matches && (
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-[11px]"
            onClick={() => setExpanded((value) => !value)}
            aria-expanded={expanded}
          >
            {expanded ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
            {expanded ? "Collapse" : "View all"}
          </Button>
        )}
      </div>

      {expanded && matchesQuery.hasNextPage && (
        <div className="border-t border-border/70 p-2">
          <Button
            variant="outline"
            size="sm"
            className="w-full"
            disabled={matchesQuery.isFetchingNextPage}
            onClick={() => matchesQuery.fetchNextPage()}
          >
            {matchesQuery.isFetchingNextPage && <Loader2 className="size-3.5 animate-spin" />}
            Load more matches
          </Button>
        </div>
      )}
    </article>
  )
}

export function TextSearchPanel({ caseId }: { caseId: string }) {
  const textSearchTerm = useEvidenceStore((state) => state.textSearchTerm)
  const search = useEvidenceTextSearch(caseId, textSearchTerm)
  const [viewerTarget, setViewerTarget] = useState<ViewerTarget | null>(null)
  const trimmedQuery = textSearchTerm.trim()
  const firstPage = search.data?.pages[0]
  const documents = search.data?.pages.flatMap((page) => page.documents) ?? []

  const openHit = (document: EvidenceTextSearchDocument, hit: EvidenceTextSearchHit) => {
    setViewerTarget({
      evidenceId: document.evidence_id,
      documentName: document.document_name,
      page: hit.page_number ?? 1,
      navigationKey: hit.id,
    })
  }

  let content: React.ReactNode
  if (!trimmedQuery) {
    content = (
      <div className="flex h-full flex-col items-center justify-center px-8 text-center">
        <span className="mb-4 flex size-11 items-center justify-center rounded-full border border-primary/20 bg-primary/8 text-primary">
          <Search className="size-5" />
        </span>
        <p className="text-sm font-semibold">Search document text across this case</p>
        <p className="mt-1 max-w-xs text-xs leading-5 text-muted-foreground">
          Enter an exact name, phrase, account number, or other literal text. Results are grouped by document.
        </p>
      </div>
    )
  } else if (trimmedQuery.length < 2) {
    content = (
      <div className="flex h-full items-center justify-center px-8 text-center text-xs text-muted-foreground">
        Enter at least 2 characters to search the case.
      </div>
    )
  } else if (search.isLoading || search.isDebouncing) {
    content = (
      <div className="flex h-full items-center justify-center gap-2 text-xs text-muted-foreground">
        <Loader2 className="size-4 animate-spin text-primary" />
        Searching exact document text…
      </div>
    )
  } else if (search.isError) {
    content = (
      <div className="flex h-full flex-col items-center justify-center px-8 text-center">
        <AlertCircle className="size-7 text-destructive" />
        <p className="mt-3 text-sm font-semibold">Search couldn’t be completed</p>
        <p className="mt-1 text-xs text-muted-foreground">Your query is still here. Retry when you’re ready.</p>
        <Button variant="outline" size="sm" className="mt-4" onClick={() => search.refetch()}>
          Retry search
        </Button>
      </div>
    )
  } else if (!firstPage || firstPage.total_documents === 0) {
    content = (
      <div className="flex h-full flex-col items-center justify-center px-8 text-center">
        <Search className="size-7 text-muted-foreground/50" />
        <p className="mt-3 text-sm font-semibold">No exact matches</p>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">
          Check punctuation and spacing, or try a shorter literal phrase.
        </p>
        {firstPage && firstPage.searchable_documents < firstPage.case_documents && (
          <p className="mt-4 rounded-md bg-muted px-3 py-2 text-[11px] text-muted-foreground">
            Searchable text is available for {firstPage.searchable_documents} of {firstPage.case_documents} case documents.
          </p>
        )}
      </div>
    )
  } else {
    content = (
      <div className="h-full overflow-y-auto">
        <div className="sticky top-0 z-10 space-y-2 border-b border-border bg-card/95 px-3 py-3 backdrop-blur-sm">
          <div className="flex items-baseline justify-between gap-3">
            <p className="text-sm font-semibold">
              {firstPage.total_matches.toLocaleString()} {firstPage.total_matches === 1 ? "match" : "matches"} across {firstPage.total_documents.toLocaleString()} {firstPage.total_documents === 1 ? "document" : "documents"}
            </p>
          </div>
          {documents.length < firstPage.total_documents && (
            <p className="font-mono text-[10px] tabular-nums text-muted-foreground">
              Showing {documents.length} of {firstPage.total_documents} matching documents
            </p>
          )}
          {firstPage.searchable_documents < firstPage.case_documents && (
            <p className="rounded-md border border-border bg-muted/40 px-2.5 py-2 text-[11px] leading-4 text-muted-foreground">
              Searchable text is available for {firstPage.searchable_documents} of {firstPage.case_documents} case documents.
            </p>
          )}
        </div>

        <div className="space-y-2.5 p-3">
          {documents.map((document) => (
            <DocumentResultCard
              key={document.evidence_id}
              document={document}
              query={search.debouncedQuery}
              onOpen={openHit}
            />
          ))}
          {search.hasNextPage && (
            <Button
              variant="outline"
              size="sm"
              className="w-full"
              disabled={search.isFetchingNextPage}
              onClick={() => search.fetchNextPage()}
            >
              {search.isFetchingNextPage && <Loader2 className="size-3.5 animate-spin" />}
              Load more documents
            </Button>
          )}
          {!search.hasNextPage && documents.length > 0 && (
            <p className="py-2 text-center font-mono text-[10px] text-muted-foreground">
              Showing {documents.length} of {firstPage.total_documents} matching documents
            </p>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className={cn("h-full", search.isFetching && !search.isLoading && "cursor-progress")}>
      {content}
      <DocumentViewer
        open={viewerTarget !== null}
        onOpenChange={(open) => !open && setViewerTarget(null)}
        documentUrl={viewerTarget ? evidenceAPI.getFileUrl(viewerTarget.evidenceId) : undefined}
        documentName={viewerTarget?.documentName}
        initialPage={viewerTarget?.page}
        navigationKey={viewerTarget?.navigationKey}
      />
    </div>
  )
}
