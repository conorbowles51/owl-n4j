import { useState } from "react"
import { Link, useParams, useSearchParams } from "react-router-dom"
import {
  AlertTriangle,
  Archive,
  ArrowLeft,
  ArrowUpRight,
  GitBranch,
  Plus,
  Search,
  X,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { EmptyState } from "@/components/ui/empty-state"
import { Input } from "@/components/ui/input"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { useCase } from "@/features/cases/hooks/use-cases"
import { useCasePermissions } from "@/features/cases/hooks/use-case-permissions"
import { cn } from "@/lib/cn"
import { useDossiers } from "../hooks"
import { DossierCreateSheet } from "./DossierCreateSheet"
import { DossierDetailSheet } from "./DossierDetailSheet"
import { DossierIcon } from "./DossierIcon"
import { dossierTypeLabel } from "../dossier-type"
import { PhoneIdentitiesTab } from "./PhoneIdentitiesTab"

const TYPES = [
  "person",
  "organisation",
  "device",
  "vehicle",
  "address",
  "event",
  "other",
]

export function DossiersPage() {
  const { id: caseId = "" } = useParams()
  const [searchParams, setSearchParams] = useSearchParams()
  const search = searchParams.get("q") ?? ""
  const rawOffset = Number(searchParams.get("offset") ?? 0)
  const offset =
    Number.isSafeInteger(rawOffset) && rawOffset > 0 ? rawOffset : 0
  const type = TYPES.includes(searchParams.get("type") ?? "")
    ? searchParams.get("type")!
    : "all"
  const linkage = ["linked", "unlinked", "deleted"].includes(
    searchParams.get("linkage") ?? ""
  )
    ? searchParams.get("linkage")!
    : "all"
  const archived = searchParams.get("archived") === "true"
  const filtered = Boolean(
    search || type !== "all" || linkage !== "all" || archived
  )
  const updateFilters = (values: Record<string, string | null>) => {
    const next = new URLSearchParams(searchParams)
    next.delete("offset")
    Object.entries(values).forEach(([key, value]) =>
      value ? next.set(key, value) : next.delete(key)
    )
    setSearchParams(next, { replace: true })
  }
  const resetFilters = () =>
    updateFilters({ q: null, type: null, linkage: null, archived: null })
  const setOffset = (value: number) =>
    updateFilters({ offset: value ? String(value) : null })
  const selected = searchParams.get("dossier")
  const tab =
    searchParams.get("tab") === "phone-identities"
      ? "phone-identities"
      : "dossiers"
  const [createOpen, setCreateOpen] = useState(false)
  const caseQuery = useCase(caseId)
  const { canEdit } = useCasePermissions(caseQuery.data)
  const query = useDossiers({
    caseId,
    q: search || undefined,
    dossierType: type === "all" ? undefined : type,
    linkageState: linkage === "all" ? undefined : linkage,
    includeArchived: archived,
    limit: 100,
    offset,
  })
  const dossiers = query.data?.dossiers ?? []
  const setSelected = (dossierId: string | null) => {
    const next = new URLSearchParams(searchParams)
    if (dossierId) next.set("dossier", dossierId)
    else next.delete("dossier")
    setSearchParams(next, { replace: true })
  }
  const setTab = (value: "dossiers" | "phone-identities") => {
    const next = new URLSearchParams(searchParams)
    if (value === "phone-identities") next.set("tab", value)
    else next.delete("tab")
    setSearchParams(next, { replace: true })
  }
  if (!caseId) return <EmptyState title="No case selected" />
  return (
    <div className="flex h-full min-w-0 flex-col bg-background">
      <header className="shrink-0 px-5 pb-6 pt-6 sm:px-8 sm:pt-8">
        <div className="mx-auto max-w-6xl">
          <Link
            to={`/cases/${caseId}/workspace`}
            className="mb-4 inline-flex min-h-10 items-center gap-2 text-xs text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="size-3.5" /> Workspace
          </Link>
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="mb-2 text-[10px] font-semibold uppercase tracking-[.18em] text-muted-foreground">
                Subjects in this case
              </p>
              <h1 className="font-display text-3xl font-semibold tracking-tight">
                Dossiers
              </h1>
              <p className="mt-2 max-w-xl text-sm leading-relaxed text-muted-foreground">
                Bring the evidence and your casework together around each
                subject.
              </p>
            </div>
            {canEdit && (
              <Button
                className="min-h-10"
                variant="primary"
                onClick={() => setCreateOpen(true)}
              >
                <Plus className="size-4" /> New Dossier
              </Button>
            )}
          </div>
        </div>
      </header>
      <nav
        aria-label="Dossier views"
        className="flex shrink-0 gap-5 border-b border-border/75 px-5 sm:px-8"
      >
        {(
          [
            ["dossiers", "Dossiers"],
            ["phone-identities", "Phone identities"],
          ] as const
        ).map(([value, words]) => (
          <button
            key={value}
            type="button"
            aria-current={tab === value ? "page" : undefined}
            onClick={() => setTab(value)}
            className={cn(
              "min-h-11 border-b-2 px-1 text-sm font-medium transition-colors",
              tab === value
                ? "border-brand-500 text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            {words}
          </button>
        ))}
      </nav>
      {tab === "phone-identities" ? (
        <PhoneIdentitiesTab
          caseId={caseId}
          canEdit={canEdit}
          onOpenDossier={setSelected}
        />
      ) : (
        <>
          <div className="flex shrink-0 flex-wrap items-center gap-3 px-5 py-4 sm:px-8">
            <div className="relative min-w-56 flex-1">
              <Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                aria-label="Search dossiers"
                value={search}
                onChange={(event) => {
                  updateFilters({ q: event.target.value })
                }}
                placeholder="Search subjects…"
                className="h-10 bg-transparent pl-8 text-sm"
              />
            </div>
            <Select
              value={type}
              onValueChange={(value) => {
                updateFilters({ type: value === "all" ? null : value })
              }}
            >
              <SelectTrigger
                aria-label="Subject type"
                className="h-10 w-40 text-xs"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All subject types</SelectItem>
                {TYPES.map((item) => (
                  <SelectItem key={item} value={item}>
                    {dossierTypeLabel(item)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select
              value={linkage}
              onValueChange={(value) => {
                updateFilters({ linkage: value === "all" ? null : value })
              }}
            >
              <SelectTrigger
                aria-label="Graph linkage"
                className="h-10 w-36 text-xs"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Any linkage</SelectItem>
                <SelectItem value="linked">Graph linked</SelectItem>
                <SelectItem value="unlinked">Unlinked</SelectItem>
                <SelectItem value="deleted">Entity deleted</SelectItem>
              </SelectContent>
            </Select>
            <label className="flex min-h-10 items-center gap-2 px-1 text-xs text-muted-foreground">
              <Checkbox
                checked={archived}
                onCheckedChange={(value) => {
                  updateFilters({ archived: value === true ? "true" : null })
                }}
              />{" "}
              Include archived
            </label>
            {filtered && (
              <Button
                variant="ghost"
                className="min-h-10 text-xs"
                onClick={resetFilters}
              >
                <X className="size-3.5" /> Clear filters
              </Button>
            )}
          </div>
          <ScrollArea className="min-h-0 flex-1">
            <div className="mx-auto max-w-6xl px-5 pb-12 pt-2 sm:px-8">
              {query.isError ? (
                <div role="alert" className="space-y-3 py-10 text-center">
                  <p>Dossiers could not be loaded.</p>
                  <Button
                    variant="outline"
                    onClick={() => void query.refetch()}
                  >
                    Retry dossiers
                  </Button>
                </div>
              ) : query.isLoading ? (
                <div className="flex justify-center py-20">
                  <LoadingSpinner />
                </div>
              ) : dossiers.length ? (
                <>
                  <div className="flex items-center justify-between border-b border-border/75 pb-3 text-[11px] text-muted-foreground">
                    <span>
                      {query.data?.total.toLocaleString()} Dossier
                      {query.data?.total === 1 ? "" : "s"}
                    </span>
                    <span>Recently updated first</span>
                  </div>
                  <div className="divide-y divide-border/60">
                    {dossiers.map((dossier) => (
                      <button
                        key={dossier.id}
                        type="button"
                        onClick={() => setSelected(dossier.id)}
                        className={cn(
                          "group flex w-full items-center gap-4 py-5 text-left transition-colors hover:bg-muted/35 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring sm:gap-5 sm:px-2",
                          selected === dossier.id && "bg-muted/40"
                        )}
                      >
                        <DossierIcon type={dossier.dossier_type} />
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                            <h2 className="break-words text-sm font-semibold">
                              {dossier.display_name}
                            </h2>
                            <span className="text-[11px] text-muted-foreground">
                              {dossierTypeLabel(dossier.dossier_type)}
                            </span>
                            {dossier.archived_at && (
                              <Badge variant="outline">
                                <Archive className="size-3" /> Archived
                              </Badge>
                            )}
                          </div>
                          {!!dossier.roles.length && (
                            <p className="mt-1 text-xs text-muted-foreground">
                              {dossier.roles
                                .map((role) => role.name)
                                .join(" · ")}
                            </p>
                          )}
                          {(dossier.importance || dossier.summary) && (
                            <p className="mt-1.5 line-clamp-2 max-w-3xl text-xs leading-relaxed text-muted-foreground">
                              {dossier.importance || dossier.summary}
                            </p>
                          )}
                          {(dossier.needs_link_review ||
                            dossier.linkage_state === "deleted") && (
                            <span className="mt-2 inline-flex items-center gap-1 text-[11px] text-amber-700 dark:text-amber-400">
                              <AlertTriangle className="size-3" />{" "}
                              {dossier.linkage_state === "deleted"
                                ? "Graph entity deleted"
                                : "Graph link needs review"}
                            </span>
                          )}
                        </div>
                        {dossier.linkage_state === "linked" && (
                          <span className="hidden items-center gap-1.5 text-[11px] text-muted-foreground sm:inline-flex">
                            <GitBranch className="size-3.5" /> Graph linked
                          </span>
                        )}
                        <ArrowUpRight
                          aria-hidden="true"
                          className="size-4 shrink-0 text-muted-foreground/50 transition-colors group-hover:text-foreground"
                        />
                      </button>
                    ))}
                  </div>
                  {(query.data?.total ?? 0) > 100 && (
                    <div className="mt-5 flex items-center justify-between gap-2 text-xs">
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={offset === 0}
                        onClick={() => setOffset(Math.max(0, offset - 100))}
                      >
                        Previous dossiers
                      </Button>
                      <span>
                        {offset + 1}–{Math.min(offset + 100, query.data!.total)}{" "}
                        of {query.data!.total}
                      </span>
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={offset + 100 >= query.data!.total}
                        onClick={() => setOffset(offset + 100)}
                      >
                        Next dossiers
                      </Button>
                    </div>
                  )}
                </>
              ) : (
                <EmptyState
                  title={
                    offset > 0
                      ? "No dossiers on this page"
                      : filtered
                        ? "No matching dossiers"
                        : "No dossiers yet"
                  }
                  description={
                    filtered
                      ? "Try a different name or clear your filters."
                      : "Create a dossier for a person, organisation or other subject. Collect relevant work here as the investigation develops."
                  }
                  action={
                    offset > 0 ? (
                      <Button variant="outline" onClick={() => setOffset(0)}>
                        Return to first page
                      </Button>
                    ) : filtered ? (
                      <Button variant="outline" onClick={resetFilters}>
                        Clear filters
                      </Button>
                    ) : canEdit ? (
                      <Button
                        variant="primary"
                        onClick={() => setCreateOpen(true)}
                      >
                        <Plus className="size-4" /> Create first Dossier
                      </Button>
                    ) : undefined
                  }
                />
              )}
            </div>
          </ScrollArea>
        </>
      )}
      <DossierCreateSheet
        key={createOpen ? "open" : "closed"}
        caseId={caseId}
        open={createOpen}
        onOpenChange={setCreateOpen}
        onOpenExisting={setSelected}
      />
      <DossierDetailSheet
        key={`detail-${selected ?? "closed"}`}
        caseId={caseId}
        dossierId={selected}
        open={Boolean(selected)}
        onOpenChange={(value) => {
          if (!value) setSelected(null)
        }}
        canEdit={canEdit}
      />
    </div>
  )
}
