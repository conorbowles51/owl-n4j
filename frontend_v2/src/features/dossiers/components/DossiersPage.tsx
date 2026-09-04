import { useMemo, useState } from "react"
import { useParams, useSearchParams } from "react-router-dom"
import {
  AlertTriangle,
  Archive,
  ContactRound,
  GitBranch,
  Link2Off,
  Plus,
  Search,
  UsersRound,
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
  const [search, setSearch] = useState("")
  const [type, setType] = useState("all")
  const [linkage, setLinkage] = useState("all")
  const [archived, setArchived] = useState(false)
  const selected = searchParams.get("dossier")
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
  })
  const dossiers = useMemo(() => query.data?.dossiers ?? [], [query.data])
  const setSelected = (dossierId: string | null) => {
    const next = new URLSearchParams(searchParams)
    if (dossierId) next.set("dossier", dossierId)
    else next.delete("dossier")
    setSearchParams(next, { replace: true })
  }
  if (!caseId) return <EmptyState title="No case selected" />
  return (
    <div className="flex h-full min-w-0 flex-col bg-background">
      <header className="relative overflow-hidden border-b border-border bg-card px-4 py-4 sm:px-6">
        <div className="pointer-events-none absolute inset-y-0 right-0 w-96 bg-[radial-gradient(circle_at_right,rgba(14,165,233,.08),transparent_68%)]" />
        <div className="relative flex items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <ContactRound className="size-4 text-brand-600" />
              <h1 className="font-display text-base font-semibold">Dossiers</h1>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              Investigator-curated casework around the subjects who matter.
            </p>
          </div>
          {canEdit ? (
            <Button variant="primary" onClick={() => setCreateOpen(true)}>
              <Plus className="size-4" /> New Dossier
            </Button>
          ) : null}
        </div>
      </header>
      <div className="flex flex-wrap items-center gap-2 border-b border-border bg-panel px-4 py-3 sm:px-6">
        <div className="relative min-w-56 flex-1">
          <Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search names and investigator summaries…"
            className="h-8 pl-8 text-xs"
          />
        </div>
        <Select value={type} onValueChange={setType}>
          <SelectTrigger className="h-8 w-40 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All subject types</SelectItem>
            {TYPES.map((item) => (
              <SelectItem key={item} value={item}>
                {item}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={linkage} onValueChange={setLinkage}>
          <SelectTrigger className="h-8 w-36 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Any linkage</SelectItem>
            <SelectItem value="linked">Graph linked</SelectItem>
            <SelectItem value="unlinked">Unlinked</SelectItem>
            <SelectItem value="deleted">Entity deleted</SelectItem>
          </SelectContent>
        </Select>
        <label className="flex items-center gap-2 px-1 text-xs text-muted-foreground">
          <Checkbox
            checked={archived}
            onCheckedChange={(value) => setArchived(value === true)}
          />{" "}
          Archived
        </label>
      </div>
      <ScrollArea className="min-h-0 flex-1">
        <div className="mx-auto max-w-6xl p-4 sm:p-6">
          {query.isLoading ? (
            <div className="flex justify-center py-20">
              <LoadingSpinner />
            </div>
          ) : dossiers.length ? (
            <>
              <div className="mb-3 flex items-center justify-between text-[11px] text-muted-foreground">
                <span>
                  {query.data?.total.toLocaleString()} Dossier
                  {query.data?.total === 1 ? "" : "s"}
                </span>
                <span>People shown first by default</span>
              </div>
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {dossiers.map((dossier) => (
                  <button
                    key={dossier.id}
                    type="button"
                    onClick={() => setSelected(dossier.id)}
                    className={cn(
                      "group relative min-h-44 overflow-hidden rounded-xl border border-border bg-card p-4 text-left shadow-sm transition hover:-translate-y-0.5 hover:border-brand-300 hover:shadow-md",
                      selected === dossier.id &&
                        "border-brand-400 ring-2 ring-brand-100 dark:ring-brand-500/15"
                    )}
                  >
                    <div className="pointer-events-none absolute -right-10 -top-10 size-28 rounded-full bg-brand-100/50 blur-2xl dark:bg-brand-500/10" />
                    <div className="relative flex items-start gap-3">
                      <div className="flex size-10 shrink-0 items-center justify-center rounded-lg border border-border bg-muted/50">
                        <UsersRound className="size-5 text-muted-foreground" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                          {dossier.dossier_type}
                        </p>
                        <h2 className="mt-0.5 truncate text-sm font-semibold">
                          {dossier.display_name}
                        </h2>
                      </div>
                      {dossier.archived_at ? (
                        <Archive className="size-4 text-muted-foreground" />
                      ) : null}
                    </div>
                    <div className="relative mt-3 flex flex-wrap gap-1">
                      {dossier.roles.slice(0, 3).map((role) => (
                        <Badge key={role.id} variant="outline">
                          {role.name}
                        </Badge>
                      ))}
                      {dossier.linkage_state === "linked" ? (
                        <Badge variant="success">
                          <GitBranch className="size-3" /> Linked
                        </Badge>
                      ) : (
                        <Badge variant="warning">
                          <Link2Off className="size-3" /> Unlinked
                        </Badge>
                      )}
                      {dossier.needs_link_review ? (
                        <Badge variant="danger">
                          <AlertTriangle className="size-3" /> Review link
                        </Badge>
                      ) : null}
                    </div>
                    <p className="relative mt-3 line-clamp-3 text-xs leading-relaxed text-muted-foreground">
                      {dossier.summary ||
                        dossier.importance ||
                        "No investigator brief yet."}
                    </p>
                  </button>
                ))}
              </div>
            </>
          ) : (
            <EmptyState
              title="No Dossiers yet"
              description="Promote an important graph entity, or begin an unlinked Dossier for a subject not yet present in evidence."
              action={
                canEdit ? (
                  <Button variant="primary" onClick={() => setCreateOpen(true)}>
                    <Plus className="size-4" /> Create first Dossier
                  </Button>
                ) : undefined
              }
            />
          )}
        </div>
      </ScrollArea>
      <DossierCreateSheet
        key={createOpen ? "open" : "closed"}
        caseId={caseId}
        open={createOpen}
        onOpenChange={setCreateOpen}
      />
      <DossierDetailSheet
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
