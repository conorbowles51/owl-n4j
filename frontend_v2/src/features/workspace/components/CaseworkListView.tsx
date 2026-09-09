import { useEffect, useMemo, useState } from "react"
import {
  Archive,
  ArrowDownUp,
  ChevronLeft,
  ChevronRight,
  Clock3,
  Filter,
  FileText,
  Lightbulb,
  Loader2,
  Plus,
  Search,
  ShieldCheck,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { cn } from "@/lib/cn"
import type {
  CaseworkEntry,
  CaseworkEntryType,
  CaseworkListParams,
  FindingSignificance,
} from "../casework-api"
import {
  caseworkTitle,
  ENTRY_LABELS,
  FINDING_STATES,
  formatCaseworkDate,
  THEORY_STATES,
} from "../casework-utils"
import {
  useCaseworkAuthors,
  useCaseworkEntries,
} from "../hooks/use-casework"
import { useCurrentCaseworkLinks } from "../hooks/use-current-casework-links"
import { ReviewBadge } from "./CaseworkBadges"
import { CaseworkDetailSheet } from "./CaseworkDetailSheet"
import { CaseworkEditor } from "./CaseworkEditor"
import { RelationshipBadge } from "./CaseworkBadges"

interface CaseworkListViewProps {
  caseId: string
  entryType: CaseworkEntryType
  canEdit: boolean
  initialSelectedEntryId?: string | null
}

const PAGE_SIZE = 25

function recentDate(value: string) {
  if (value === "all") return undefined
  const days = Number(value)
  const date = new Date()
  date.setDate(date.getDate() - days)
  return date.toISOString()
}

export function CaseworkListView({
  caseId,
  entryType,
  canEdit,
  initialSelectedEntryId = null,
}: CaseworkListViewProps) {
  const [query, setQuery] = useState("")
  const [lifecycle, setLifecycle] = useState("all")
  const [significance, setSignificance] = useState("all")
  const [confidence, setConfidence] = useState("all")
  const [author, setAuthor] = useState("all")
  const [recent, setRecent] = useState("all")
  const [sort, setSort] = useState("updated_at:desc")
  const [includeDeleted, setIncludeDeleted] = useState(false)
  const [offset, setOffset] = useState(0)
  const [selectedEntryId, setSelectedEntryId] = useState<string | null>(initialSelectedEntryId)
  const [createOpen, setCreateOpen] = useState(false)
  const currentSelection = useCurrentCaseworkLinks(caseId)
  const authorsQuery = useCaseworkAuthors(caseId)

  useEffect(() => setOffset(0), [author, confidence, includeDeleted, lifecycle, query, recent, significance, sort])
  useEffect(() => setSelectedEntryId(initialSelectedEntryId), [initialSelectedEntryId])

  const params = useMemo<CaseworkListParams>(() => {
    const [sortBy, direction] = sort.split(":") as [
      NonNullable<CaseworkListParams["sort_by"]>,
      NonNullable<CaseworkListParams["sort_direction"]>,
    ]
    const confidenceValues = confidence === "all" ? [] : confidence.split("-").map(Number)
    return {
      entry_type: entryType,
      q: query.trim() || undefined,
      lifecycle_state: lifecycle === "all" ? undefined : lifecycle,
      significance:
        entryType === "finding" && significance !== "all"
          ? (significance as FindingSignificance)
          : undefined,
      confidence_min:
        entryType === "theory" && confidenceValues.length ? confidenceValues[0] : undefined,
      confidence_max:
        entryType === "theory" && confidenceValues.length ? confidenceValues[1] : undefined,
      author_user_id: author === "all" ? undefined : author,
      updated_since: recentDate(recent),
      include_deleted: includeDeleted,
      sort_by: sortBy,
      sort_direction: direction,
      limit: PAGE_SIZE,
      offset,
    }
  }, [author, confidence, entryType, includeDeleted, lifecycle, offset, query, recent, significance, sort])
  const entriesQuery = useCaseworkEntries(caseId, params)
  const entries = entriesQuery.data?.entries ?? []
  const total = entriesQuery.data?.total ?? 0
  const page = Math.floor(offset / PAGE_SIZE) + 1
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const lifecycleStates = entryType === "finding" ? FINDING_STATES : THEORY_STATES

  const resetFilters = () => {
    setQuery("")
    setLifecycle("all")
    setSignificance("all")
    setConfidence("all")
    setAuthor("all")
    setRecent("all")
    setIncludeDeleted(false)
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            {entryType === "finding" ? <ShieldCheck className="size-5 text-muted-foreground" /> : entryType === "note" ? <FileText className="size-5 text-muted-foreground" /> : <Lightbulb className="size-5 text-muted-foreground" />}
            <h2 className="font-display text-xl font-semibold">{ENTRY_LABELS[entryType]}s</h2>
          </div>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
            {entryType === "finding"
              ? "Established investigative conclusions, ranked by their significance to the case."
              : entryType === "note" ? "Investigator notes captured in the notebook and across the case." : "Working explanations that can strengthen, weaken, or become findings as evidence develops."}
          </p>
        </div>
        {canEdit && (
          <Button size="sm" onClick={() => setCreateOpen(true)}><Plus className="size-3.5" /> New {ENTRY_LABELS[entryType].toLowerCase()}</Button>
        )}
      </div>

      <div className="rounded-xl border border-border bg-card p-3 shadow-sm">
        <div className="flex flex-wrap gap-2">
          <div className="relative min-w-[220px] flex-1">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={`Search ${ENTRY_LABELS[entryType].toLowerCase()}s`} className="h-8 pl-8 text-xs" />
          </div>
          {entryType !== "note" && <Select value={lifecycle} onValueChange={setLifecycle}>
            <SelectTrigger size="sm" className="w-[145px] max-sm:w-full"><SelectValue placeholder="Lifecycle" /></SelectTrigger>
            <SelectContent><SelectItem value="all">All lifecycles</SelectItem>{lifecycleStates.map((state) => <SelectItem key={state} value={state}>{state.replace(/^./, (letter) => letter.toUpperCase())}</SelectItem>)}</SelectContent>
          </Select>}
          {entryType === "finding" ? (
            <Select value={significance} onValueChange={setSignificance}>
              <SelectTrigger size="sm" className="w-[145px] max-sm:w-full"><SelectValue placeholder="Significance" /></SelectTrigger>
              <SelectContent><SelectItem value="all">All significance</SelectItem><SelectItem value="high">High</SelectItem><SelectItem value="medium">Medium</SelectItem><SelectItem value="low">Low</SelectItem></SelectContent>
            </Select>
          ) : entryType === "theory" ? (
            <Select value={confidence} onValueChange={setConfidence}>
              <SelectTrigger size="sm" className="w-[145px] max-sm:w-full"><SelectValue placeholder="Confidence" /></SelectTrigger>
              <SelectContent><SelectItem value="all">All confidence</SelectItem><SelectItem value="0-25">0–25%</SelectItem><SelectItem value="30-65">30–65%</SelectItem><SelectItem value="70-100">70–100%</SelectItem></SelectContent>
            </Select>
          ) : null}
          <Select value={author} onValueChange={setAuthor}>
            <SelectTrigger size="sm" className="w-[155px] max-sm:w-full"><SelectValue placeholder="Author" /></SelectTrigger>
            <SelectContent><SelectItem value="all">All authors</SelectItem>{authorsQuery.data?.map((item) => <SelectItem key={item.user_id} value={item.user_id}>{item.label}</SelectItem>)}</SelectContent>
          </Select>
          <Select value={recent} onValueChange={setRecent}>
            <SelectTrigger size="sm" className="w-[145px] max-sm:w-full"><Clock3 className="size-3" /><SelectValue /></SelectTrigger>
            <SelectContent><SelectItem value="all">Any activity</SelectItem><SelectItem value="1">Last 24 hours</SelectItem><SelectItem value="7">Last 7 days</SelectItem><SelectItem value="30">Last 30 days</SelectItem></SelectContent>
          </Select>
          <Select value={sort} onValueChange={setSort}>
            <SelectTrigger size="sm" className="w-[150px] max-sm:w-full"><ArrowDownUp className="size-3" /><SelectValue /></SelectTrigger>
            <SelectContent><SelectItem value="updated_at:desc">Recently updated</SelectItem><SelectItem value="created_at:desc">Recently created</SelectItem><SelectItem value="title:asc">Title A–Z</SelectItem>{entryType === "finding" ? <SelectItem value="significance:asc">Significance</SelectItem> : <SelectItem value="confidence:desc">Confidence</SelectItem>}</SelectContent>
          </Select>
        </div>
        <div className="mt-2 flex flex-wrap items-center justify-between gap-2 border-t border-border pt-2">
          <Label htmlFor={`${entryType}-deleted`} className="flex items-center gap-2 text-xs font-normal text-muted-foreground"><Switch id={`${entryType}-deleted`} checked={includeDeleted} onCheckedChange={setIncludeDeleted} /><Archive className="size-3.5" /> Include deleted</Label>
          <div className="flex items-center gap-2"><span className="text-[11px] text-muted-foreground">{total.toLocaleString()} result{total === 1 ? "" : "s"}</span><Button type="button" variant="ghost" size="sm" className="h-7 text-[11px]" onClick={resetFilters}><Filter className="size-3" /> Reset</Button></div>
        </div>
      </div>

      {entriesQuery.isLoading ? (
        <div className="flex min-h-72 items-center justify-center gap-2 text-sm text-muted-foreground"><Loader2 className="size-4 animate-spin" /> Loading casework</div>
      ) : entriesQuery.isError ? (
        <div className="rounded-xl border border-destructive/40 bg-destructive/5 p-8 text-center"><p className="text-sm font-medium">Casework could not be loaded.</p><Button className="mt-3" size="sm" variant="outline" onClick={() => entriesQuery.refetch()}>Try again</Button></div>
      ) : entries.length === 0 ? (
        <div className="flex min-h-72 flex-col items-center justify-center rounded-xl border border-dashed border-border bg-card/40 px-6 text-center">
          {entryType === "finding" ? <ShieldCheck className="size-9 text-muted-foreground/40" /> : entryType === "note" ? <FileText className="size-9 text-muted-foreground/40" /> : <Lightbulb className="size-9 text-muted-foreground/40" />}
          <h3 className="mt-3 text-sm font-semibold">No matching {ENTRY_LABELS[entryType].toLowerCase()}s</h3>
          <p className="mt-1 max-w-sm text-xs leading-relaxed text-muted-foreground">Adjust the filters or capture new casework from here or the persistent Notebook.</p>
          {canEdit && <Button className="mt-4" size="sm" variant="secondary" onClick={() => setCreateOpen(true)}><Plus className="size-3.5" /> New {ENTRY_LABELS[entryType].toLowerCase()}</Button>}
        </div>
      ) : (
        <div className="grid gap-2">
          {entries.map((entry: CaseworkEntry) => (
            <button
              key={entry.id}
              type="button"
              onClick={() => setSelectedEntryId(entry.id)}
              className={cn(
                "group grid w-full gap-3 rounded-xl border border-border bg-card p-4 text-left shadow-sm transition-[border-color,box-shadow,transform] hover:-translate-y-px hover:border-ring/30 hover:shadow-md sm:grid-cols-[minmax(0,1fr)_auto]",
                entry.deleted_at && "opacity-65",
              )}
            >
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-1.5">
                  <h3 className="mr-1 min-w-0 truncate text-sm font-semibold text-foreground">{caseworkTitle(entry)}</h3>
                  {entry.lifecycle_state && <Badge variant="slate" className="capitalize">{entry.lifecycle_state}</Badge>}
                  {entry.significance && <Badge variant="outline" className="capitalize">{entry.significance}</Badge>}
                  {entry.confidence !== null && entry.confidence !== undefined && <Badge variant="outline">{entry.confidence}%</Badge>}
                  <ReviewBadge entry={entry} />
                  {entry.deleted_at && <Badge variant="destructive">Deleted</Badge>}
                </div>
                <p className="mt-1.5 line-clamp-2 text-xs leading-relaxed text-muted-foreground">{entry.body}</p>
                <div className="mt-2 flex flex-wrap items-center gap-1.5">
                  {entry.links.slice(0, 3).map((link) => <RelationshipBadge key={link.id} relationship={link.relationship} />)}
                  {entry.links.length > 3 && <span className="text-[10px] text-muted-foreground">+{entry.links.length - 3} links</span>}
                  {entry.tags.slice(0, 3).map((tag) => <Badge key={tag} variant="outline" className="px-1.5 py-0 text-[10px]">{tag}</Badge>)}
                </div>
              </div>
              <div className="flex items-end justify-between gap-3 text-[11px] text-muted-foreground sm:flex-col sm:items-end">
                <span>{entry.author_name || entry.author_email || "Unknown investigator"}</span>
                <span className="flex items-center gap-1"><Clock3 className="size-3" /> {formatCaseworkDate(entry.updated_at || entry.created_at)}</span>
              </div>
            </button>
          ))}
        </div>
      )}

      {total > PAGE_SIZE && (
        <nav className="flex items-center justify-between border-t border-border pt-3" aria-label={`${ENTRY_LABELS[entryType]} pagination`}>
          <Button variant="outline" size="sm" disabled={offset === 0} onClick={() => setOffset((current) => Math.max(0, current - PAGE_SIZE))}><ChevronLeft className="size-3.5" /> Previous</Button>
          <span className="text-xs text-muted-foreground">Page {page} of {pageCount}</span>
          <Button variant="outline" size="sm" disabled={offset + PAGE_SIZE >= total} onClick={() => setOffset((current) => current + PAGE_SIZE)}>Next <ChevronRight className="size-3.5" /></Button>
        </nav>
      )}

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader><DialogTitle>New {ENTRY_LABELS[entryType].toLowerCase()}</DialogTitle><DialogDescription>Use the same casework language and linked material available from the Notebook.</DialogDescription></DialogHeader>
          <CaseworkEditor caseId={caseId} initialType={entryType} currentSelection={currentSelection} canEdit={canEdit} onCancel={() => setCreateOpen(false)} onSaved={(entry) => { setCreateOpen(false); setSelectedEntryId(entry.id) }} />
        </DialogContent>
      </Dialog>

      <CaseworkDetailSheet caseId={caseId} entryId={selectedEntryId} open={!!selectedEntryId} canEdit={canEdit} onOpenChange={(open) => !open && setSelectedEntryId(null)} onOpenEntry={setSelectedEntryId} />
    </div>
  )
}
