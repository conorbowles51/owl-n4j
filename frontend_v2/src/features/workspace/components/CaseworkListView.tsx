import { lazy, Suspense, useEffect, useMemo, useState } from "react"
import {
  Archive,
  ArrowDownUp,
  ChevronLeft,
  ChevronRight,
  Clock3,
  FileText,
  FolderOpen,
  Layers3,
  Lightbulb,
  Link2,
  Loader2,
  Plus,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  X,
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
  CaseworkEntryType,
  CaseworkListParams,
  FindingSignificance,
} from "../casework-api"
import {
  caseworkTitle,
  ENTRY_LABELS,
  ENTRY_PLURAL_LABELS,
  FINDING_STATES,
  formatCaseworkDate,
  THEORY_STATES,
} from "../casework-utils"
import { useCaseworkAuthors, useCaseworkEntries } from "../hooks/use-casework"
import { useCurrentCaseworkLinks } from "../hooks/use-current-casework-links"
import { ReviewBadge } from "./CaseworkBadges"
import { CaseworkDetailSheet } from "./CaseworkDetailSheet"
import { CaseworkEditor } from "./CaseworkEditor"
import {
  DossierSourceViewer,
  type DossierSource,
} from "@/features/dossiers/components/DossierSourceViewer"

const DossierDetailSheet = lazy(() =>
  import("@/features/dossiers/components/DossierDetailSheet").then((m) => ({
    default: m.DossierDetailSheet,
  }))
)
export type CaseworkFilter = CaseworkEntryType | "all"
interface CaseworkListViewProps {
  caseId: string
  entryType?: CaseworkFilter
  onEntryTypeChange?: (type: CaseworkFilter) => void
  canEdit: boolean
  initialSelectedEntryId?: string | null
}
const PAGE_SIZE = 25
const TYPE_ICONS = { note: FileText, finding: ShieldCheck, theory: Lightbulb }
const TYPE_DESCRIPTIONS = {
  note: "Observations and notes captured as you investigate.",
  finding: "Conclusions supported by the material in your case.",
  theory: "Working explanations to test as the evidence develops.",
}

function recentDate(value: string) {
  if (value === "all") return undefined
  const date = new Date()
  date.setDate(date.getDate() - Number(value))
  return date.toISOString()
}

export function CaseworkListView({
  caseId,
  entryType = "all",
  onEntryTypeChange,
  canEdit,
  initialSelectedEntryId = null,
}: CaseworkListViewProps) {
  const [localType, setLocalType] = useState(entryType)
  const activeType = onEntryTypeChange ? entryType : localType
  const [query, setQuery] = useState("")
  const [lifecycle, setLifecycle] = useState("all")
  const [significance, setSignificance] = useState("all")
  const [confidence, setConfidence] = useState("all")
  const [author, setAuthor] = useState("all")
  const [recent, setRecent] = useState("all")
  const [sort, setSort] = useState("updated_at:desc")
  const [includeDeleted, setIncludeDeleted] = useState(false)
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [offset, setOffset] = useState(0)
  const [selectedEntryId, setSelectedEntryId] = useState<string | null>(
    initialSelectedEntryId
  )
  const [createOpen, setCreateOpen] = useState(false)
  const [createDirty, setCreateDirty] = useState(false)
  const [source, setSource] = useState<DossierSource | null>(null)
  const [dossierId, setDossierId] = useState<string | null>(null)
  const currentSelection = useCurrentCaseworkLinks(caseId)
  const authorsQuery = useCaseworkAuthors(caseId)

  useEffect(() => setLocalType(entryType), [entryType])
  useEffect(() => {
    setLifecycle("all")
    setSignificance("all")
    setConfidence("all")
    setSort("updated_at:desc")
  }, [activeType])
  useEffect(
    () => setOffset(0),
    [
      activeType,
      author,
      confidence,
      includeDeleted,
      lifecycle,
      query,
      recent,
      significance,
      sort,
    ]
  )
  useEffect(
    () => setSelectedEntryId(initialSelectedEntryId),
    [initialSelectedEntryId]
  )

  const params = useMemo<CaseworkListParams>(() => {
    const [sortBy, direction] = sort.split(":") as [
      NonNullable<CaseworkListParams["sort_by"]>,
      NonNullable<CaseworkListParams["sort_direction"]>,
    ]
    const confidenceValues =
      confidence === "all" ? [] : confidence.split("-").map(Number)
    return {
      entry_type: activeType === "all" ? undefined : activeType,
      q: query.trim() || undefined,
      lifecycle_state:
        activeType !== "all" && activeType !== "note" && lifecycle !== "all"
          ? lifecycle
          : undefined,
      significance:
        activeType === "finding" && significance !== "all"
          ? (significance as FindingSignificance)
          : undefined,
      confidence_min: activeType === "theory" ? confidenceValues[0] : undefined,
      confidence_max: activeType === "theory" ? confidenceValues[1] : undefined,
      author_user_id: author === "all" ? undefined : author,
      updated_since: recentDate(recent),
      include_deleted: includeDeleted,
      sort_by: sortBy,
      sort_direction: direction,
      limit: PAGE_SIZE,
      offset,
    }
  }, [
    activeType,
    author,
    confidence,
    includeDeleted,
    lifecycle,
    offset,
    query,
    recent,
    significance,
    sort,
  ])
  const entriesQuery = useCaseworkEntries(caseId, params)
  const entries = entriesQuery.data?.entries ?? []
  const total = entriesQuery.data?.total ?? 0
  useEffect(() => {
    if (
      entriesQuery.data &&
      !entriesQuery.isPlaceholderData &&
      offset > 0 &&
      offset >= total
    ) {
      setOffset(Math.max(0, Math.ceil(total / PAGE_SIZE) - 1) * PAGE_SIZE)
    }
  }, [entriesQuery.data, entriesQuery.isPlaceholderData, offset, total])
  const label =
    activeType === "all"
      ? "casework"
      : ENTRY_PLURAL_LABELS[activeType].toLowerCase()
  const createLabel =
    activeType === "all"
      ? "New casework"
      : `New ${ENTRY_LABELS[activeType].toLowerCase()}`
  const advancedCount = [
    author !== "all",
    recent !== "all",
    includeDeleted,
    (activeType === "finding" || activeType === "theory") &&
      lifecycle !== "all",
    activeType === "finding" && significance !== "all",
    activeType === "theory" && confidence !== "all",
  ].filter(Boolean).length
  const filtered = !!query.trim() || advancedCount > 0
  const resetFilters = () => {
    setQuery("")
    setLifecycle("all")
    setSignificance("all")
    setConfidence("all")
    setAuthor("all")
    setRecent("all")
    setIncludeDeleted(false)
    setOffset(0)
  }
  const changeType = (type: CaseworkFilter) => {
    setLifecycle("all")
    setSignificance("all")
    setConfidence("all")
    setSort("updated_at:desc")
    setOffset(0)
    if (onEntryTypeChange) onEntryTypeChange(type)
    else setLocalType(type)
  }
  const closeComposer = (next: boolean) => {
    if (
      !next &&
      createDirty &&
      !window.confirm("Discard your unsaved casework?")
    )
      return
    setCreateOpen(next)
    if (!next) setCreateDirty(false)
  }

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="font-display text-2xl font-semibold tracking-tight">
            Casework
          </h2>
          <p className="mt-2 max-w-xl text-sm leading-relaxed text-muted-foreground">
            Bring your observations, working theories and conclusions together.
          </p>
        </div>
        {canEdit && (
          <Button className="h-10" onClick={() => setCreateOpen(true)}>
            <Plus className="size-4" /> {createLabel}
          </Button>
        )}
      </header>

      <div className="space-y-4">
        <div
          className="flex flex-wrap gap-1 border-b border-border/70 pb-3"
          role="group"
          aria-label="Casework type"
        >
          {(["all", "note", "finding", "theory"] as const).map((type) => {
            const Icon = type === "all" ? Layers3 : TYPE_ICONS[type]
            return (
              <button
                key={type}
                type="button"
                aria-pressed={activeType === type}
                onClick={() => changeType(type)}
                className={cn(
                  "inline-flex min-h-10 items-center gap-2 rounded-md px-3 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50",
                  activeType === type
                    ? "bg-primary/10 font-medium text-primary"
                    : "text-muted-foreground hover:bg-muted/50 hover:text-foreground"
                )}
              >
                <Icon aria-hidden="true" className="size-4" />
                {type === "all" ? "All casework" : ENTRY_PLURAL_LABELS[type]}
              </button>
            )
          })}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-0 basis-full sm:flex-1 sm:basis-auto">
            <Search
              aria-hidden="true"
              className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
            />
            <Input
              aria-label={`Search ${label}`}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={`Search ${label}`}
              className="h-10 bg-transparent pl-9"
            />
          </div>
          <Button
            variant={advancedCount ? "secondary" : "ghost"}
            className="h-10"
            aria-expanded={filtersOpen}
            aria-controls="casework-filters"
            onClick={() => setFiltersOpen(!filtersOpen)}
          >
            <SlidersHorizontal className="size-4" /> Filters{" "}
            {advancedCount > 0 && (
              <span className="tabular-nums">{advancedCount}</span>
            )}
          </Button>
          <Select value={sort} onValueChange={setSort}>
            <SelectTrigger
              aria-label="Sort casework"
              className="h-10 w-auto gap-2 border-transparent bg-transparent shadow-none"
            >
              <ArrowDownUp aria-hidden="true" className="size-3.5" />
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="updated_at:desc">Recently updated</SelectItem>
              <SelectItem value="created_at:desc">Recently created</SelectItem>
              <SelectItem value="title:asc">Title A–Z</SelectItem>
              {activeType === "finding" && (
                <SelectItem value="significance:asc">Significance</SelectItem>
              )}
              {activeType === "theory" && (
                <SelectItem value="confidence:desc">Confidence</SelectItem>
              )}
            </SelectContent>
          </Select>
        </div>
        {filtersOpen && (
          <div
            id="casework-filters"
            className="flex flex-wrap items-center gap-3 border-y border-border/60 py-4"
          >
            {(activeType === "finding" || activeType === "theory") && (
              <Select value={lifecycle} onValueChange={setLifecycle}>
                <SelectTrigger
                  aria-label="Filter by status"
                  className="h-10 w-[165px] max-sm:w-full"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All statuses</SelectItem>
                  {(activeType === "finding"
                    ? FINDING_STATES
                    : THEORY_STATES
                  ).map((state) => (
                    <SelectItem key={state} value={state}>
                      {state.replace(/^./, (letter) => letter.toUpperCase())}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
            {activeType === "finding" && (
              <Select value={significance} onValueChange={setSignificance}>
                <SelectTrigger
                  aria-label="Filter by significance"
                  className="h-10 w-[165px] max-sm:w-full"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All significance</SelectItem>
                  <SelectItem value="high">High</SelectItem>
                  <SelectItem value="medium">Medium</SelectItem>
                  <SelectItem value="low">Low</SelectItem>
                </SelectContent>
              </Select>
            )}
            {activeType === "theory" && (
              <Select value={confidence} onValueChange={setConfidence}>
                <SelectTrigger
                  aria-label="Filter by confidence"
                  className="h-10 w-[165px] max-sm:w-full"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All confidence</SelectItem>
                  <SelectItem value="0-25">0–25%</SelectItem>
                  <SelectItem value="26-69">26–69%</SelectItem>
                  <SelectItem value="70-100">70–100%</SelectItem>
                </SelectContent>
              </Select>
            )}
            <Select value={author} onValueChange={setAuthor}>
              <SelectTrigger
                aria-label="Filter by author"
                className="h-10 w-[165px] max-sm:w-full"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All authors</SelectItem>
                {authorsQuery.data?.map((item) => (
                  <SelectItem key={item.user_id} value={item.user_id}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={recent} onValueChange={setRecent}>
              <SelectTrigger
                aria-label="Filter by activity"
                className="h-10 w-[165px] max-sm:w-full"
              >
                <Clock3 className="size-3.5" />
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Any activity</SelectItem>
                <SelectItem value="1">Last 24 hours</SelectItem>
                <SelectItem value="7">Last 7 days</SelectItem>
                <SelectItem value="30">Last 30 days</SelectItem>
              </SelectContent>
            </Select>
            <Label
              htmlFor="casework-deleted"
              className="flex min-h-10 items-center gap-2 text-xs font-normal text-muted-foreground"
            >
              <Switch
                id="casework-deleted"
                checked={includeDeleted}
                onCheckedChange={setIncludeDeleted}
              />
              <Archive className="size-3.5" /> Include deleted
            </Label>
            {authorsQuery.isError && (
              <span className="text-xs text-destructive">
                Authors unavailable.{" "}
                <button
                  type="button"
                  className="underline"
                  onClick={() => void authorsQuery.refetch()}
                >
                  Retry
                </button>
              </span>
            )}
          </div>
        )}
        <div className="flex min-h-6 flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
          <span>
            {activeType === "all"
              ? "Your investigation, in one place"
              : TYPE_DESCRIPTIONS[activeType]}
          </span>
          <div className="flex items-center gap-3">
            {filtered && (
              <button
                type="button"
                onClick={resetFilters}
                className="inline-flex min-h-10 items-center gap-1 hover:text-foreground"
              >
                <X className="size-3.5" /> Clear filters
              </button>
            )}
            <span aria-live="polite" className="tabular-nums">
              {entriesQuery.isLoading
                ? "Loading…"
                : `${total.toLocaleString()} ${total === 1 ? "item" : "items"}`}
            </span>
          </div>
        </div>
      </div>

      {entriesQuery.isLoading ? (
        <div
          role="status"
          className="flex min-h-64 items-center justify-center gap-2 text-sm text-muted-foreground"
        >
          <Loader2 className="size-4 animate-spin" /> Loading casework
        </div>
      ) : entriesQuery.isError ? (
        <div role="alert" className="py-16 text-center">
          <p className="text-sm font-medium">Casework could not be loaded.</p>
          <Button
            className="mt-3 h-10"
            variant="outline"
            onClick={() => void entriesQuery.refetch()}
          >
            Try again
          </Button>
        </div>
      ) : entries.length === 0 ? (
        <div className="flex min-h-64 flex-col items-center justify-center px-6 py-12 text-center">
          <Layers3 className="size-8 text-muted-foreground/40" />
          <h3 className="mt-4 text-base font-medium">
            {filtered ? `No matching ${label}` : `No ${label} yet`}
          </h3>
          <p className="mt-2 max-w-sm text-sm leading-relaxed text-muted-foreground">
            {filtered
              ? "Try another search or clear your filters."
              : "Start with an observation. Link it to evidence or a dossier, and build your understanding as you go."}
          </p>
          {filtered ? (
            <Button
              className="mt-5 h-10"
              variant="outline"
              onClick={resetFilters}
            >
              Clear filters
            </Button>
          ) : (
            canEdit && (
              <Button
                className="mt-5 h-10"
                variant="outline"
                onClick={() => setCreateOpen(true)}
              >
                <Plus className="size-4" /> {createLabel}
              </Button>
            )
          )}
        </div>
      ) : (
        <div
          className="divide-y divide-border/70 border-y border-border/70"
          aria-label="Casework list"
        >
          {entries.map((entry) => {
            const Icon = TYPE_ICONS[entry.entry_type]
            const namedLinks = [...entry.links]
              .sort(
                (a, b) =>
                  Number(b.target_type === "dossier") -
                  Number(a.target_type === "dossier")
              )
              .slice(0, 2)
            return (
              <button
                key={entry.id}
                type="button"
                onClick={() => setSelectedEntryId(entry.id)}
                className={cn(
                  "group flex w-full min-w-0 gap-3 px-1 py-5 text-left transition-colors hover:bg-muted/35 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/50 sm:gap-4 sm:px-3",
                  entry.deleted_at && "opacity-60"
                )}
              >
                <span
                  className={cn(
                    "mt-0.5 grid size-9 shrink-0 place-items-center rounded-lg",
                    entry.entry_type === "finding"
                      ? "bg-status-success-soft text-status-success"
                      : entry.entry_type === "theory"
                        ? "bg-status-warning-soft text-status-warning"
                        : "bg-muted text-muted-foreground"
                  )}
                >
                  <Icon aria-hidden="true" className="size-4" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="mb-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-muted-foreground">
                    <span>{ENTRY_LABELS[entry.entry_type]}</span>
                    {entry.lifecycle_state && (
                      <>
                        <span aria-hidden="true">·</span>
                        <span className="capitalize">
                          {entry.lifecycle_state}
                        </span>
                      </>
                    )}
                    {entry.entry_type === "finding" && entry.significance && (
                      <span className="font-medium">
                        ·{" "}
                        {entry.significance === "high"
                          ? "High significance"
                          : `${entry.significance} significance`}
                      </span>
                    )}
                    {entry.confidence != null && (
                      <span>· {entry.confidence}% confidence</span>
                    )}
                    <ReviewBadge entry={entry} />
                    {entry.deleted_at && (
                      <Badge variant="destructive">Deleted</Badge>
                    )}
                  </span>
                  <span className="block text-sm font-semibold leading-6 text-foreground [overflow-wrap:anywhere]">
                    {caseworkTitle(entry)}
                  </span>
                  <span className="mt-1 block line-clamp-2 text-sm leading-relaxed text-muted-foreground">
                    {entry.body}
                  </span>
                  {(namedLinks.length > 0 || entry.tags.length > 0) && (
                    <span className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
                      {namedLinks.map((link) => (
                        <span
                          key={link.id}
                          className="inline-flex min-w-0 max-w-full items-center gap-1.5"
                        >
                          {link.target_type === "dossier" ? (
                            <FolderOpen className="size-3.5 shrink-0" />
                          ) : (
                            <Link2 className="size-3.5 shrink-0" />
                          )}
                          <span className="truncate">
                            {link.target_label || "Linked item"}
                          </span>
                        </span>
                      ))}
                      {entry.links.length > 2 && (
                        <span>+{entry.links.length - 2} linked</span>
                      )}
                      {entry.tags.slice(0, 2).map((tag) => (
                        <span key={tag} className="max-w-full truncate">
                          #{tag}
                        </span>
                      ))}
                    </span>
                  )}
                  <span className="mt-3 block text-[11px] text-muted-foreground sm:hidden">
                    {entry.author_name || entry.author_email || "Investigator"}{" "}
                    · {formatCaseworkDate(entry.updated_at || entry.created_at)}
                  </span>
                </span>
                <span className="hidden w-36 shrink-0 flex-col items-end gap-2 pt-1 text-right text-[11px] text-muted-foreground sm:flex">
                  <span>
                    {formatCaseworkDate(entry.updated_at || entry.created_at)}
                  </span>
                  <span className="max-w-full truncate">
                    {entry.author_name || entry.author_email || "Investigator"}
                  </span>
                  <ChevronRight className="mt-3 size-4 opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100" />
                </span>
              </button>
            )
          })}
        </div>
      )}

      {total > PAGE_SIZE && (
        <nav
          className="flex items-center justify-between gap-2"
          aria-label="Casework pagination"
        >
          <Button
            variant="ghost"
            className="h-10"
            disabled={offset === 0}
            onClick={() =>
              setOffset((current) => Math.max(0, current - PAGE_SIZE))
            }
          >
            <ChevronLeft className="size-4" /> Previous
          </Button>
          <span className="text-xs tabular-nums text-muted-foreground">
            Page {Math.floor(offset / PAGE_SIZE) + 1} of{" "}
            {Math.max(1, Math.ceil(total / PAGE_SIZE))}
          </span>
          <Button
            variant="ghost"
            className="h-10"
            disabled={offset + PAGE_SIZE >= total}
            onClick={() => setOffset((current) => current + PAGE_SIZE)}
          >
            Next <ChevronRight className="size-4" />
          </Button>
        </nav>
      )}

      <Dialog open={createOpen} onOpenChange={closeComposer}>
        <DialogContent
          guardTypedContent={false}
          className="max-h-[92vh] overflow-y-auto sm:max-w-2xl"
        >
          <DialogHeader>
            <DialogTitle>{createLabel}</DialogTitle>
            <DialogDescription>
              Capture an observation, develop a theory or record a finding. Link
              it to the people and evidence it concerns.
            </DialogDescription>
          </DialogHeader>
          <CaseworkEditor
            caseId={caseId}
            initialType={activeType === "all" ? "note" : activeType}
            currentSelection={currentSelection}
            canEdit={canEdit}
            onDirtyChange={setCreateDirty}
            onCancel={() => closeComposer(false)}
            onSaved={(entry) => {
              setCreateDirty(false)
              setCreateOpen(false)
              setSelectedEntryId(entry.id)
            }}
          />
        </DialogContent>
      </Dialog>
      <CaseworkDetailSheet
        caseId={caseId}
        entryId={selectedEntryId}
        open={!!selectedEntryId}
        canEdit={canEdit}
        onOpenChange={(open) => !open && setSelectedEntryId(null)}
        onOpenEntry={setSelectedEntryId}
        onOpenDossier={setDossierId}
        onOpenEvidence={(evidenceId, name, anchor) =>
          setSource({
            evidenceId,
            name,
            page: typeof anchor.page === "number" ? anchor.page : undefined,
            time:
              typeof anchor.timestamp === "number"
                ? anchor.timestamp
                : undefined,
          })
        }
      />
      {source && (
        <DossierSourceViewer
          caseId={caseId}
          source={source}
          onClose={() => setSource(null)}
        />
      )}
      {dossierId && (
        <Suspense fallback={<p role="status">Loading dossier…</p>}>
          <DossierDetailSheet
            caseId={caseId}
            dossierId={dossierId}
            open
            canEdit={canEdit}
            onOpenChange={(open) => !open && setDossierId(null)}
          />
        </Suspense>
      )}
    </div>
  )
}
