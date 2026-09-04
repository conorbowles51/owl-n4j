import { CaseworkHistory } from "./CaseworkHistory"
import { useEffect, useMemo, useState } from "react"
import { useNavigate } from "react-router-dom"
import {
  ArchiveRestore,
  ArrowRight,
  Edit3,
  FileText,
  GitBranch,
  Link2,
  Loader2,
  RotateCcw,
  Sparkles,
  Trash2,
} from "lucide-react"
import { toast } from "sonner"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Markdown } from "@/components/ui/markdown"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { Textarea } from "@/components/ui/textarea"
import { useEvidenceStore } from "@/features/evidence/evidence.store"
import { useGraphStore } from "@/stores/graph.store"
import { useUIStore } from "@/stores/ui.store"
import type { CaseworkLink, FindingSignificance } from "../casework-api"
import {
  caseworkTitle,
  FINDING_STATES,
  formatCaseworkDate,
  THEORY_STATES,
} from "../casework-utils"
import {
  useCaseworkEntry,
  useChangeCaseworkLifecycle,
  useConvertTheory,
  useDeleteCaseworkEntry,
  useRestoreCaseworkEntry,
} from "../hooks/use-casework"
import { useCurrentCaseworkLinks } from "../hooks/use-current-casework-links"
import { CaseworkEditor } from "./CaseworkEditor"
import { RelationshipBadge, ReviewBadge } from "./CaseworkBadges"
import { WorkspaceAIPanel } from "@/features/workspace-ai/components/WorkspaceAIPanel"

interface CaseworkDetailSheetProps {
  caseId: string
  entryId: string | null
  open: boolean
  canEdit: boolean
  onOpenChange: (open: boolean) => void
  onOpenEntry?: (entryId: string) => void
}

function labelState(value?: string | null) {
  if (!value) return ""
  return value.replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase())
}

function anchorLabel(anchor: Record<string, unknown>) {
  const parts: string[] = []
  if (anchor.page) parts.push(`Page ${anchor.page}`)
  if (anchor.timestamp) parts.push(String(anchor.timestamp))
  if (anchor.quote) parts.push(`“${String(anchor.quote).slice(0, 80)}”`)
  if (anchor.segment_id) parts.push(`Segment ${anchor.segment_id}`)
  return parts.join(" · ")
}

export function CaseworkDetailSheet({
  caseId,
  entryId,
  open,
  canEdit,
  onOpenChange,
  onOpenEntry,
}: CaseworkDetailSheetProps) {
  const navigate = useNavigate()
  const [editing, setEditing] = useState(false)
  const [lifecycleDialog, setLifecycleDialog] = useState(false)
  const [nextLifecycle, setNextLifecycle] = useState("")
  const [lifecycleRationale, setLifecycleRationale] = useState("")
  const [conversionDialog, setConversionDialog] = useState(false)
  const [conversionTitle, setConversionTitle] = useState("")
  const [conversionBody, setConversionBody] = useState("")
  const [conversionSignificance, setConversionSignificance] =
    useState<FindingSignificance>("medium")
  const entryQuery = useCaseworkEntry(caseId, entryId ?? undefined, true)
  const entry = entryQuery.data
  const lifecycleMutation = useChangeCaseworkLifecycle(caseId)
  const conversionMutation = useConvertTheory(caseId)
  const deleteMutation = useDeleteCaseworkEntry(caseId)
  const restoreMutation = useRestoreCaseworkEntry(caseId)
  const currentSelection = useCurrentCaseworkLinks(caseId)
  const selectNodes = useGraphStore((state) => state.selectNodes)
  const expandGraphPanelTo = useUIStore((state) => state.expandGraphPanelTo)
  const openEvidenceDetail = useEvidenceStore((state) => state.openDetail)

  useEffect(() => {
    if (!open) setEditing(false)
  }, [open])

  useEffect(() => {
    if (entry) {
      setConversionTitle(entry.title ?? "")
      setConversionBody(entry.body)
    }
  }, [entry])

  const evidenceGroups = useMemo(() => {
    const groups = {
      supports: [] as CaseworkLink[],
      contradicts: [] as CaseworkLink[],
      context: [] as CaseworkLink[],
      unclassified: [] as CaseworkLink[],
    }
    if (!entry) return groups
    for (const link of entry.links.filter((item) => item.target_type === "evidence")) {
      groups[link.relationship ?? "unclassified"].push(link)
    }
    return groups
  }, [entry])

  const openLink = (targetType: string, targetId: string) => {
    if (targetType === "evidence") {
      navigate(`/cases/${caseId}/evidence`)
      openEvidenceDetail(targetId)
    } else if (targetType === "graph_entity") {
      navigate(`/cases/${caseId}/graph`)
      selectNodes([targetId])
      expandGraphPanelTo("detail")
    } else if (targetType === "dossier") {
      navigate(`/cases/${caseId}/dossiers?dossier=${encodeURIComponent(targetId)}`)
    } else if (targetType === "entry") {
      onOpenEntry?.(targetId)
    }
  }

  const changeLifecycle = async () => {
    if (!entry || !nextLifecycle) return
    try {
      await lifecycleMutation.mutateAsync({
        entryId: entry.id,
        version: entry.version,
        state: nextLifecycle,
        rationale: lifecycleRationale.trim() || undefined,
      })
      await entryQuery.refetch()
      setLifecycleDialog(false)
      setLifecycleRationale("")
      toast.success("Lifecycle updated")
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not update lifecycle")
    }
  }

  const convertTheory = async () => {
    if (!entry || !conversionTitle.trim() || !conversionBody.trim()) return
    try {
      const result = await conversionMutation.mutateAsync({
        entryId: entry.id,
        version: entry.version,
        significance: conversionSignificance,
        draft: { title: conversionTitle.trim(), body: conversionBody.trim() },
      })
      setConversionDialog(false)
      toast.success("Finding created and linked to the source theory")
      onOpenEntry?.(result.finding.id)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not convert theory")
    }
  }

  const deleteEntry = async () => {
    if (!entry || !window.confirm(`Move “${caseworkTitle(entry)}” to deleted casework?`)) return
    try {
      await deleteMutation.mutateAsync({ entryId: entry.id, version: entry.version })
      await entryQuery.refetch()
      toast.success("Casework deleted. It can be restored.")
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not delete casework")
    }
  }

  const restoreEntry = async () => {
    if (!entry) return
    try {
      await restoreMutation.mutateAsync({ entryId: entry.id, version: entry.version })
      await entryQuery.refetch()
      toast.success("Casework restored")
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not restore casework")
    }
  }

  return (
    <>
      <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetContent className="w-[min(920px,96vw)] gap-0 p-0 sm:max-w-[920px]">
          <SheetHeader className="border-b border-border px-5 py-4 pr-12">
            <SheetTitle>{entry ? caseworkTitle(entry) : "Casework"}</SheetTitle>
            <SheetDescription>
              {entry ? `${labelState(entry.entry_type)} · version ${entry.version}` : "Loading casework"}
            </SheetDescription>
          </SheetHeader>
          <ScrollArea className="min-h-0 flex-1">
            {entryQuery.isLoading ? (
              <div className="flex min-h-72 items-center justify-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin" /> Loading casework
              </div>
            ) : entryQuery.isError || !entry ? (
              <div className="p-8 text-center text-sm text-muted-foreground">This entry could not be loaded.</div>
            ) : editing ? (
              <div className="p-5">
                <CaseworkEditor
                  key={`${entry.id}:${entry.version}`}
                  caseId={caseId}
                  entry={entry}
                  currentSelection={currentSelection}
                  canEdit={canEdit && !entry.deleted_at}
                  onCancel={() => setEditing(false)}
                  onReload={() => entryQuery.refetch()}
                  onSaved={async () => {
                    await entryQuery.refetch()
                    setEditing(false)
                  }}
                />
              </div>
            ) : (
              <div className="space-y-7 p-5">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="outline">{labelState(entry.entry_type)}</Badge>
                  {entry.lifecycle_state && <Badge variant="slate">{labelState(entry.lifecycle_state)}</Badge>}
                  {entry.significance && <Badge variant="outline">{labelState(entry.significance)} significance</Badge>}
                  {entry.confidence !== null && entry.confidence !== undefined && <Badge variant="outline">{entry.confidence}% confidence</Badge>}
                  <ReviewBadge entry={entry} />
                  {entry.deleted_at && <Badge variant="destructive">Deleted</Badge>}
                  {entry.needs_migration_review && <Badge variant="outline">Migration review needed</Badge>}
                </div>

                <div className="flex flex-wrap gap-2">
                  {canEdit && !entry.deleted_at && (
                    <Button size="sm" onClick={() => setEditing(true)}><Edit3 className="size-3.5" /> Edit</Button>
                  )}
                  {canEdit && entry.lifecycle_state && !entry.deleted_at && (
                    <Button variant="outline" size="sm" onClick={() => { setNextLifecycle(entry.lifecycle_state ?? ""); setLifecycleDialog(true) }}>
                      <RotateCcw className="size-3.5" /> Change lifecycle
                    </Button>
                  )}
                  {canEdit && entry.entry_type === "theory" && entry.lifecycle_state !== "converted" && !entry.deleted_at && (
                    <Button variant="outline" size="sm" onClick={() => setConversionDialog(true)}>
                      <ArrowRight className="size-3.5" /> Convert to finding
                    </Button>
                  )}
                  {canEdit && (entry.deleted_at ? (
                    <Button variant="outline" size="sm" onClick={restoreEntry} disabled={restoreMutation.isPending}><ArchiveRestore className="size-3.5" /> Restore</Button>
                  ) : (
                    <Button variant="ghost" size="sm" className="text-muted-foreground hover:text-destructive" onClick={deleteEntry} disabled={deleteMutation.isPending}><Trash2 className="size-3.5" /> Delete</Button>
                  ))}
                </div>

                {entry.source_theory_entry_id && (
                  <button type="button" className="flex w-full items-center gap-3 rounded-lg border border-violet-200 bg-violet-50/70 p-3 text-left dark:border-violet-900 dark:bg-violet-950/30" onClick={() => onOpenEntry?.(entry.source_theory_entry_id!)}>
                    <Sparkles className="size-4 shrink-0 text-violet-600 dark:text-violet-300" />
                    <span className="min-w-0 flex-1"><span className="block text-xs font-semibold">Created from a theory</span><span className="block text-xs text-muted-foreground">Open the source theory and its conversion history</span></span>
                    <ArrowRight className="size-4" />
                  </button>
                )}

                <article>
                  <Markdown content={entry.body} className="text-sm leading-7" />
                </article>

                {!!entry.tags.length && (
                  <div className="flex flex-wrap gap-1.5">{entry.tags.map((tag) => <Badge key={tag} variant="slate">{tag}</Badge>)}</div>
                )}

                {entry.entry_type === "theory" && entry.confidence_rationale && (
                  <section className="rounded-lg border border-border bg-muted/25 p-3">
                    <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Latest confidence rationale</h3>
                    <p className="mt-1.5 text-sm leading-relaxed">{entry.confidence_rationale}</p>
                  </section>
                )}

                {entry.entry_type === "theory" && !entry.deleted_at ? (
                  <WorkspaceAIPanel
                    caseId={caseId}
                    targetType="theory"
                    targetId={entry.id}
                    canEdit={canEdit}
                  />
                ) : null}

                {!!entry.links.length && (
                  <section className="space-y-3">
                    <div><h3 className="text-sm font-semibold">Linked material</h3><p className="text-xs text-muted-foreground">Relationship assessments apply only to this entry.</p></div>
                    <div className="divide-y divide-border">
                      {entry.links.map((link) => {
                        const anchor = anchorLabel(link.source_anchor)
                        return (
                          <button
                            key={link.id}
                            type="button"
                            disabled={!(["evidence", "graph_entity", "entry", "dossier"] as string[]).includes(link.target_type)}
                            className="flex min-h-10 w-full min-w-0 items-center gap-2 py-2 text-left transition-colors enabled:hover:bg-muted/35 disabled:cursor-default"
                            onClick={() => openLink(link.target_type, link.target_id)}
                          >
                            {link.target_type === "evidence" ? <FileText className="mt-0.5 size-4 shrink-0 text-muted-foreground" /> : link.target_type === "graph_entity" ? <GitBranch className="mt-0.5 size-4 shrink-0 text-muted-foreground" /> : <Link2 className="mt-0.5 size-4 shrink-0 text-muted-foreground" />}
                            <span className="flex min-w-0 flex-1 flex-wrap items-center justify-between gap-2"><span className="truncate text-xs font-semibold">{link.target_label || "Linked item"}</span><span className="mt-1 flex flex-wrap items-center gap-1.5"><RelationshipBadge relationship={link.relationship} />{anchor && <span className="text-[10px] text-muted-foreground">{anchor}</span>}</span></span>
                          </button>
                        )
                      })}
                    </div>
                  </section>
                )}

                {entry.links.some((link) => link.target_type === "evidence") && (
                  <details className="space-y-3 border-t border-border pt-3">
                    <summary className="cursor-pointer text-xs font-semibold">Compare supporting and contradicting evidence</summary>
                    <div className="grid gap-3 md:grid-cols-2">
                      {(["supports", "contradicts"] as const).map((relationship) => (
                        <div key={relationship} className="rounded-lg border border-border bg-muted/15 p-3">
                          <RelationshipBadge relationship={relationship} />
                          <div className="mt-2 space-y-1.5">
                            {evidenceGroups[relationship].length ? evidenceGroups[relationship].map((link) => (
                              <button key={link.id} type="button" className="block w-full truncate rounded-md bg-background px-2.5 py-2 text-left text-xs font-medium hover:bg-muted" onClick={() => openLink("evidence", link.target_id)}>{link.target_label || "Evidence"}</button>
                            )) : <p className="py-2 text-xs text-muted-foreground">No evidence classified here.</p>}
                          </div>
                        </div>
                      ))}
                    </div>
                    {(evidenceGroups.context.length > 0 || evidenceGroups.unclassified.length > 0) && (
                      <p className="text-xs text-muted-foreground">Also linked: {evidenceGroups.context.length} context and {evidenceGroups.unclassified.length} unclassified item(s).</p>
                    )}
                  </details>
                )}

                <CaseworkHistory key={`${entry.id}-revisions`} title="Revision history">
                  {(entry.revisions ?? []).slice().reverse().map((revision) => (
                    <div key={revision.id} className="py-2">
                      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 text-xs">
                        <span className="font-medium">Version {revision.revision_number}</span>
                        <span className="text-muted-foreground">{revision.editor_name || revision.editor_email || "Unknown investigator"} · {formatCaseworkDate(revision.created_at)}</span>
                      </div>
                      <p className="mt-1 line-clamp-1 text-xs text-muted-foreground">{revision.body}</p>
                    </div>
                  ))}
                </CaseworkHistory>
                <CaseworkHistory key={`${entry.id}-events`} title="Lifecycle events">
                  {(entry.events ?? []).slice().reverse().map((event) => (
                    <div key={event.id} className="py-2 text-xs">
                      <div className="flex flex-wrap justify-between gap-x-3 gap-y-1">
                        <span className="font-medium">{labelState(event.event_type)}</span>
                        <span className="text-muted-foreground">{event.actor_name || event.actor_email || "System"} · {formatCaseworkDate(event.created_at)}</span>
                      </div>
                      {event.rationale && <p className="mt-1 line-clamp-2 text-muted-foreground">{event.rationale}</p>}
                    </div>
                  ))}
                </CaseworkHistory>
              </div>
            )}
          </ScrollArea>
        </SheetContent>
      </Sheet>

      <Dialog open={lifecycleDialog} onOpenChange={setLifecycleDialog}>
        <DialogContent>
          <DialogHeader><DialogTitle>Change lifecycle</DialogTitle><DialogDescription>Record the investigative status of this {entry?.entry_type}. The event remains in its audit history.</DialogDescription></DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5"><Label>Status</Label><Select value={nextLifecycle} onValueChange={setNextLifecycle}><SelectTrigger className="w-full"><SelectValue /></SelectTrigger><SelectContent>{(entry?.entry_type === "finding" ? FINDING_STATES : THEORY_STATES).map((state) => <SelectItem key={state} value={state}>{labelState(state)}</SelectItem>)}</SelectContent></Select></div>
            <div className="space-y-1.5"><Label htmlFor="lifecycle-rationale">Rationale (optional)</Label><Textarea id="lifecycle-rationale" value={lifecycleRationale} onChange={(event) => setLifecycleRationale(event.target.value)} placeholder="What changed in the case?" /></div>
          </div>
          <DialogFooter><Button variant="outline" onClick={() => setLifecycleDialog(false)}>Cancel</Button><Button onClick={changeLifecycle} disabled={!nextLifecycle || lifecycleMutation.isPending}>{lifecycleMutation.isPending && <Loader2 className="size-3.5 animate-spin" />} Save lifecycle</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={conversionDialog} onOpenChange={setConversionDialog}>
        <DialogContent className="sm:max-w-xl">
          <DialogHeader><DialogTitle>Create finding from theory</DialogTitle><DialogDescription>Review the draft before saving. The original theory is marked Converted only after this finding is created successfully.</DialogDescription></DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5"><Label htmlFor="conversion-title">Finding title</Label><Input id="conversion-title" value={conversionTitle} onChange={(event) => setConversionTitle(event.target.value)} /></div>
            <div className="space-y-1.5"><Label htmlFor="conversion-body">Finding</Label><Textarea id="conversion-body" className="min-h-40" value={conversionBody} onChange={(event) => setConversionBody(event.target.value)} /></div>
            <div className="space-y-1.5"><Label>Significance</Label><Select value={conversionSignificance} onValueChange={(value: FindingSignificance) => setConversionSignificance(value)}><SelectTrigger className="w-full"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="high">High</SelectItem><SelectItem value="medium">Medium</SelectItem><SelectItem value="low">Low</SelectItem></SelectContent></Select></div>
          </div>
          <DialogFooter><Button variant="outline" onClick={() => setConversionDialog(false)}>Cancel</Button><Button onClick={convertTheory} disabled={!conversionTitle.trim() || !conversionBody.trim() || conversionMutation.isPending}>{conversionMutation.isPending ? <Loader2 className="size-3.5 animate-spin" /> : <ArrowRight className="size-3.5" />} Create finding</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
