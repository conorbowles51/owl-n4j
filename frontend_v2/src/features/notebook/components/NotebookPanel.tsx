import { useCallback, useEffect, useMemo, useState } from "react"
import {
  BookOpenText,
  Clock3,
  Edit3,
  Lightbulb,
  Loader2,
  NotebookPen,
  Plus,
  Search,
  ShieldCheck,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import { cn } from "@/lib/cn"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import { useCase } from "@/features/cases/hooks/use-cases"
import { useCasePermissions } from "@/features/cases/hooks/use-case-permissions"
import type { CaseworkEntryType, CaseworkLinkInput } from "@/features/workspace/casework-api"
import {
  caseworkTitle,
  formatCaseworkDate,
} from "@/features/workspace/casework-utils"
import { ReviewBadge } from "@/features/workspace/components/CaseworkBadges"
import { CaseworkEditor } from "@/features/workspace/components/CaseworkEditor"
import {
  useCaseworkEntries,
  useCaseworkEntry,
} from "@/features/workspace/hooks/use-casework"
import { useCurrentCaseworkLinks } from "@/features/workspace/hooks/use-current-casework-links"
import type { NotebookLinkInput } from "../api"
import { useNotebookStore } from "../notebook.store"

interface NotebookPanelProps {
  caseId: string
}

function canonicalLink(link: NotebookLinkInput): CaseworkLinkInput {
  return {
    target_type:
      link.target_type === "entity"
        ? "graph_entity"
        : link.target_type === "document"
          ? "evidence"
          : link.target_type,
    target_id: link.target_id,
    target_label: link.target_label ?? null,
    relationship: "unclassified",
    source_anchor: {},
    metadata: link.metadata ?? {},
  }
}

const typeIcons = {
  note: NotebookPen,
  finding: ShieldCheck,
  theory: Lightbulb,
}

export function NotebookPanel({ caseId }: NotebookPanelProps) {
  const user = useAuthStore((state) => state.user)
  const caseQuery = useCase(caseId)
  const { canEdit } = useCasePermissions(caseQuery.data)
  const [search, setSearch] = useState("")
  const [mineOnly, setMineOnly] = useState(false)
  const [typeFilter, setTypeFilter] = useState<"all" | CaseworkEntryType>("all")
  const [composerOpen, setComposerOpen] = useState(false)
  const [editingEntryId, setEditingEntryId] = useState<string | null>(null)
  const [newType, setNewType] = useState<CaseworkEntryType>("note")
  const [initialLinks, setInitialLinks] = useState<CaseworkLinkInput[]>([])
  const activeNoteId = useNotebookStore((state) => state.activeNoteId)
  const clearActiveNote = useNotebookStore((state) => state.clearActiveNote)
  const draftIntentId = useNotebookStore((state) => state.draftIntentId)
  const draftLinks = useNotebookStore((state) => state.draftLinks)
  const currentSelection = useCurrentCaseworkLinks(caseId)

  const params = useMemo(
    () => ({
      entry_type: typeFilter === "all" ? undefined : typeFilter,
      author_user_id: mineOnly ? user?.id : undefined,
      q: search.trim() || undefined,
      sort_by: "updated_at" as const,
      sort_direction: "desc" as const,
      limit: 50,
      offset: 0,
    }),
    [mineOnly, search, typeFilter, user?.id],
  )
  const entriesQuery = useCaseworkEntries(caseId, params)
  const entries = entriesQuery.data?.entries ?? []
  const editingQuery = useCaseworkEntry(caseId, editingEntryId ?? undefined)

  const startNew = useCallback(
    (links: CaseworkLinkInput[] = [], type: CaseworkEntryType = "note") => {
      clearActiveNote()
      setEditingEntryId(null)
      setNewType(type)
      setInitialLinks(links)
      setComposerOpen(true)
    },
    [clearActiveNote],
  )

  useEffect(() => {
    if (draftIntentId > 0) {
      startNew(draftLinks.map(canonicalLink))
    }
  }, [draftIntentId, draftLinks, startNew])

  useEffect(() => {
    if (activeNoteId) {
      setEditingEntryId(activeNoteId)
      setComposerOpen(true)
      setMineOnly(false)
      setSearch("")
    }
  }, [activeNoteId])

  const closeComposer = () => {
    setComposerOpen(false)
    setEditingEntryId(null)
    setInitialLinks([])
    clearActiveNote()
  }

  return (
    <div className="flex h-full min-w-0 flex-col bg-card">
      <div className="border-b border-border px-4 py-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <NotebookPen className="size-4 text-muted-foreground" />
              <h2 className="text-sm font-semibold">Notebook</h2>
            </div>
            <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">
              Capture notes, findings, and theories without leaving the case.
            </p>
          </div>
          {canEdit && (
            <Button size="sm" variant="secondary" onClick={() => startNew(currentSelection)}>
              <Plus className="size-3.5" /> New
            </Button>
          )}
        </div>

        <div className="mt-3 flex items-center gap-2">
          <div className="relative min-w-0 flex-1">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search casework" className="h-8 pl-8 text-xs" />
          </div>
          <div className="flex shrink-0 rounded-md border border-border bg-muted/30 p-0.5">
            {([false, true] as const).map((mine) => (
              <button key={String(mine)} type="button" onClick={() => setMineOnly(mine)} className={cn("h-6 rounded px-2 text-[11px] font-medium transition-colors", mineOnly === mine ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground")}>{mine ? "Mine" : "All"}</button>
            ))}
          </div>
        </div>
        <div className="mt-2 flex gap-1 overflow-x-auto" aria-label="Filter casework type">
          {(["all", "note", "finding", "theory"] as const).map((type) => (
            <button key={type} type="button" aria-pressed={typeFilter === type} onClick={() => setTypeFilter(type)} className={cn("rounded-full border px-2 py-0.5 text-[10px] font-medium capitalize transition-colors", typeFilter === type ? "border-foreground/20 bg-foreground text-background" : "border-border text-muted-foreground hover:text-foreground")}>{type === "all" ? "All types" : type === "theory" ? "Theories" : `${type}s`}</button>
          ))}
        </div>
      </div>

      {composerOpen && (
        <ScrollArea className="max-h-[68%] shrink-0 border-b border-border bg-muted/15">
          <div className="p-4">
            {editingEntryId && editingQuery.isLoading ? (
              <div className="flex items-center justify-center gap-2 py-10 text-xs text-muted-foreground"><Loader2 className="size-3.5 animate-spin" /> Loading casework</div>
            ) : editingEntryId && !editingQuery.data ? (
              <div className="rounded-lg border border-destructive/30 p-4 text-center text-xs text-muted-foreground">This casework entry could not be loaded.<Button variant="ghost" size="sm" className="mt-2" onClick={closeComposer}>Close</Button></div>
            ) : (
              <CaseworkEditor
                key={editingQuery.data ? `${editingQuery.data.id}:${editingQuery.data.version}` : `${newType}:${draftIntentId}`}
                caseId={caseId}
                entry={editingQuery.data}
                initialType={newType}
                initialLinks={initialLinks}
                currentSelection={currentSelection}
                canEdit={canEdit}
                compact
                onReload={() => editingQuery.refetch()}
                onCancel={closeComposer}
                onSaved={closeComposer}
              />
            )}
          </div>
        </ScrollArea>
      )}

      <ScrollArea className="min-h-0 flex-1">
        <div className="space-y-2.5 p-3">
          {entriesQuery.isLoading ? (
            <div className="flex items-center justify-center gap-2 py-10 text-sm text-muted-foreground"><Loader2 className="size-4 animate-spin" /> Loading casework</div>
          ) : entries.length === 0 ? (
            <div className="flex min-h-60 flex-col items-center justify-center rounded-lg border border-dashed border-border px-6 text-center">
              <BookOpenText className="size-8 text-muted-foreground/45" />
              <p className="mt-3 text-sm font-medium">No matching casework</p>
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">Capture an observation, conclusion, or working explanation and link it to the material behind it.</p>
              {canEdit && <Button className="mt-4" size="sm" variant="secondary" onClick={() => startNew(currentSelection)}><Plus className="size-3.5" /> Start casework</Button>}
            </div>
          ) : (
            entries.map((entry) => {
              const Icon = typeIcons[entry.entry_type]
              return (
                <article key={entry.id} className={cn("group rounded-lg border border-border bg-background p-3 transition-colors hover:border-ring/25", editingEntryId === entry.id && "border-ring/40 bg-muted/20")}>
                  <button type="button" className="block w-full text-left" onClick={() => { setEditingEntryId(entry.id); setComposerOpen(true) }}>
                    <div className="flex items-start gap-2">
                      <span className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-md bg-muted"><Icon className="size-3.5 text-muted-foreground" /></span>
                      <span className="min-w-0 flex-1">
                        <span className="flex flex-wrap items-center gap-1.5"><span className="line-clamp-2 text-sm font-semibold leading-snug">{caseworkTitle(entry)}</span>{entry.lifecycle_state && <Badge variant="slate" className="capitalize">{entry.lifecycle_state}</Badge>}<ReviewBadge entry={entry} /></span>
                        <span className="mt-1 line-clamp-2 text-xs leading-relaxed text-muted-foreground">{entry.body}</span>
                      </span>
                      {canEdit && <Edit3 className="mt-1 size-3.5 shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />}
                    </div>
                  </button>
                  <div className="mt-2 flex min-w-0 items-center justify-between gap-2 text-[11px] text-muted-foreground">
                    <span className="min-w-0 truncate">{entry.author_name || entry.author_email || "Unknown investigator"}</span>
                    <span className="flex shrink-0 items-center gap-1"><Clock3 className="size-3" />{formatCaseworkDate(entry.updated_at || entry.created_at)}</span>
                  </div>
                </article>
              )
            })
          )}
        </div>
      </ScrollArea>
    </div>
  )
}
