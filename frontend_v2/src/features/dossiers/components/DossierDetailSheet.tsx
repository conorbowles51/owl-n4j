import { useEffect, useMemo, useState } from "react"
import {
  Archive,
  ArrowDown,
  ArrowUp,
  CalendarDays,
  Camera,
  ExternalLink,
  FileText,
  GitBranch,
  Link2,
  Link2Off,
  MoreHorizontal,
  Plus,
  ShieldCheck,
  Sparkles,
  Star,
  Trash2,
  UserRound,
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
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { MarkdownSummary } from "@/components/ui/markdown-summary"
import { DocumentViewer } from "@/components/ui/document-viewer"
import { evidenceAPI } from "@/features/evidence/api"
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
  SheetTitle,
} from "@/components/ui/sheet"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Textarea } from "@/components/ui/textarea"
import { NotebookEntityPicker } from "@/features/notebook/components/NotebookEntityPicker"
import { dossiersAPI, type Dossier, type DossierMedia } from "../api"
import { useDossier, useDossierMutation } from "../hooks"
import { DossierEvidencePicker } from "./DossierEvidencePicker"
import { EvidenceImage } from "./EvidenceImage"
import { WorkspaceAIPanel } from "@/features/workspace-ai/components/WorkspaceAIPanel"

function formatDate(value?: string | null) {
  return value
    ? new Intl.DateTimeFormat(undefined, {
        dateStyle: "medium",
        timeStyle: value.includes("T") ? "short" : undefined,
      }).format(new Date(value))
    : "Date not recorded"
}

function AddMediaDialog({
  caseId,
  dossier,
  open,
  onOpenChange,
  onSaved,
}: {
  caseId: string
  dossier: Dossier
  open: boolean
  onOpenChange: (open: boolean) => void
  onSaved: () => void
}) {
  const [evidence, setEvidence] = useState<{
    id: string
    label: string
  } | null>(null)
  const [caption, setCaption] = useState("")
  const [cover, setCover] = useState(!dossier.media?.length)
  const [saving, setSaving] = useState(false)
  useEffect(() => {
    if (!open) {
      setEvidence(null)
      setCaption("")
      setCover(!dossier.media?.length)
    }
  }, [dossier.media?.length, open])
  const save = async () => {
    if (!evidence) return
    setSaving(true)
    try {
      await dossiersAPI.addMedia(dossier.id, {
        evidence_file_id: evidence.id,
        caption,
        is_cover: cover,
      })
      toast.success("Image added to Dossier")
      onSaved()
      onOpenChange(false)
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Could not add image"
      )
    } finally {
      setSaving(false)
    }
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[calc(100dvh-2rem)] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Add evidence-backed image</DialogTitle>
          <DialogDescription>
            Curate an image already held in Evidence without changing the source
            file.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          {evidence ? (
            <div className="flex items-center justify-between rounded-lg border border-border p-3">
              <div>
                <p className="break-all text-sm font-medium">
                  {evidence.label}
                </p>
                <p className="text-[11px] text-muted-foreground">
                  Source remains in Evidence
                </p>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setEvidence(null)}
              >
                Change
              </Button>
            </div>
          ) : (
            <DossierEvidencePicker
              caseId={caseId}
              selectedIds={(dossier.media ?? []).map(
                (item) => item.evidence_file_id
              )}
              onSelect={setEvidence}
            />
          )}
          <div className="grid gap-2">
            <Label>Caption</Label>
            <Input
              value={caption}
              onChange={(event) => setCaption(event.target.value)}
              placeholder="Why this image matters…"
            />
          </div>
          <label className="flex items-center gap-2 text-xs">
            <input
              type="checkbox"
              checked={cover}
              onChange={(event) => setCover(event.target.checked)}
            />{" "}
            Use as Dossier cover
          </label>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="primary"
            disabled={!evidence || saving}
            onClick={() => void save()}
          >
            {saving ? "Adding…" : "Add image"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function AssessmentDialog({
  caseId,
  dossier,
  open,
  onOpenChange,
  onSaved,
}: {
  caseId: string
  dossier: Dossier
  open: boolean
  onOpenChange: (open: boolean) => void
  onSaved: () => void
}) {
  const [category, setCategory] = useState("credibility")
  const [content, setContent] = useState("")
  const [source, setSource] = useState<{ id: string; label: string } | null>(
    null
  )
  const [saving, setSaving] = useState(false)
  useEffect(() => {
    if (!open) {
      setCategory("credibility")
      setContent("")
      setSource(null)
    }
  }, [open])
  const save = async () => {
    setSaving(true)
    try {
      await dossiersAPI.createAssessment(dossier.id, {
        category,
        content,
        assessment_date: new Date().toISOString().slice(0, 10),
        supporting_links: source
          ? [
              {
                target_type: "evidence",
                target_id: source.id,
                label: source.label,
              },
            ]
          : [],
      })
      toast.success("Assessment recorded")
      onSaved()
      onOpenChange(false)
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Could not save assessment"
      )
    } finally {
      setSaving(false)
    }
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[calc(100dvh-2rem)] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Record investigator assessment</DialogTitle>
          <DialogDescription>
            Add attributed analysis and, when available, the evidence that
            supports it.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="grid gap-2">
            <Label>Category</Label>
            <Select value={category} onValueChange={setCategory}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {[
                  "credibility",
                  "reliability",
                  "risk",
                  "strategy",
                  "classification",
                  "other",
                ].map((item) => (
                  <SelectItem key={item} value={item}>
                    {item[0].toUpperCase() + item.slice(1)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-2">
            <Label>Assessment</Label>
            <Textarea
              rows={5}
              value={content}
              onChange={(event) => setContent(event.target.value)}
              placeholder="State the investigator's assessment and reasoning…"
            />
          </div>
          <div className="space-y-2">
            <Label>
              Supporting evidence{" "}
              <span className="font-normal text-muted-foreground">
                (optional)
              </span>
            </Label>
            {source ? (
              <div className="flex justify-between rounded border border-border p-2 text-xs">
                <span className="truncate">{source.label}</span>
                <button onClick={() => setSource(null)}>Remove</button>
              </div>
            ) : (
              <DossierEvidencePicker caseId={caseId} onSelect={setSource} />
            )}
          </div>
          <p className="text-[11px] text-muted-foreground">
            Assessments are dated and attributed to you; they are not presented
            as objective evidence facts.
          </p>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="primary"
            disabled={!content.trim() || saving}
            onClick={() => void save()}
          >
            {saving ? "Saving…" : "Record assessment"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function InterviewDialog({
  caseId,
  dossier,
  open,
  onOpenChange,
  onSaved,
}: {
  caseId: string
  dossier: Dossier
  open: boolean
  onOpenChange: (open: boolean) => void
  onSaved: () => void
}) {
  const [date, setDate] = useState("")
  const [participants, setParticipants] = useState(dossier.display_name)
  const [notes, setNotes] = useState("")
  const [sources, setSources] = useState<Array<{ id: string; label: string }>>(
    []
  )
  const [saving, setSaving] = useState(false)
  useEffect(() => {
    if (!open) {
      setDate("")
      setParticipants(dossier.display_name)
      setNotes("")
      setSources([])
    }
  }, [dossier.display_name, open])
  const save = async () => {
    if (!sources.length) return
    setSaving(true)
    try {
      await dossiersAPI.createInterview(dossier.id, {
        interview_date: date ? new Date(date).toISOString() : null,
        participants: participants
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
        status: "completed",
        working_notes: notes || null,
        evidence_links: sources.map((item) => ({ evidence_file_id: item.id })),
      })
      toast.success("Interview added")
      onSaved()
      onOpenChange(false)
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Could not create interview"
      )
    } finally {
      setSaving(false)
    }
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Add interview or statement</DialogTitle>
          <DialogDescription>
            Link an existing interview transcript or statement from Evidence.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="grid gap-2">
            <Label>Date and time (optional)</Label>
            <Input
              type="datetime-local"
              value={date}
              onChange={(event) => setDate(event.target.value)}
            />
          </div>
          <div className="grid gap-2">
            <Label>Participants</Label>
            <Input
              value={participants}
              onChange={(event) => setParticipants(event.target.value)}
              placeholder="Comma-separated names"
            />
          </div>
          <div className="grid gap-2">
            <Label>Working notes</Label>
            <Textarea
              rows={5}
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label>Source evidence</Label>
            {sources.length ? (
              <div className="space-y-1">
                {sources.map((item) => (
                  <div
                    key={item.id}
                    className="flex justify-between rounded border border-border p-2 text-xs"
                  >
                    <span className="truncate">{item.label}</span>
                    <button
                      onClick={() =>
                        setSources((current) =>
                          current.filter((source) => source.id !== item.id)
                        )
                      }
                    >
                      Remove
                    </button>
                  </div>
                ))}
              </div>
            ) : null}
            <DossierEvidencePicker
              caseId={caseId}
              selectedIds={sources.map((item) => item.id)}
              onSelect={(item) => setSources((current) => [...current, item])}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="primary"
            disabled={saving || !sources.length}
            onClick={() => void save()}
          >
            {saving ? "Saving…" : "Add interview"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function MediaCard({
  dossier,
  media,
  canEdit,
  refresh,
  onMoveEarlier,
  onMoveLater,
}: {
  dossier: Dossier
  media: DossierMedia
  canEdit: boolean
  refresh: () => void
  onMoveEarlier: () => void
  onMoveLater: () => void
}) {
  const [caption, setCaption] = useState(media.caption ?? "")
  const mutation = useDossierMutation(
    dossier.case_id,
    dossier.id,
    (input: Parameters<typeof dossiersAPI.updateMedia>[2]) =>
      dossiersAPI.updateMedia(dossier.id, media.id, input)
  )
  const update = async (
    input: Parameters<typeof dossiersAPI.updateMedia>[2]
  ) => {
    try {
      await mutation.mutateAsync(input)
      refresh()
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Could not update image"
      )
    }
  }
  return (
    <article className="group overflow-hidden rounded-lg border border-border bg-card">
      <a
        href={media.evidence.file_url}
        target="_blank"
        rel="noreferrer"
        className="relative block aspect-[4/3]"
      >
        <EvidenceImage
          url={media.evidence.file_url}
          alt={media.caption || media.evidence.original_filename}
          focalX={media.focal_x}
          focalY={media.focal_y}
          className="size-full"
        />
        {media.is_cover ? (
          <Badge className="absolute left-2 top-2 bg-background/90">
            <Star className="size-3 fill-current" /> Cover
          </Badge>
        ) : null}
        <ExternalLink className="absolute bottom-2 right-2 size-4 rounded bg-background/80 p-0.5 opacity-0 shadow group-hover:opacity-100" />
      </a>
      <div className="space-y-2 p-3">
        <Input
          className="h-7 border-transparent bg-transparent px-0 text-xs font-medium focus:border-border focus:px-2"
          value={caption}
          onChange={(event) => setCaption(event.target.value)}
          onBlur={() => {
            if (caption !== (media.caption ?? "")) void update({ caption })
          }}
          placeholder="Add caption…"
        />
        <p className="truncate text-[10px] text-muted-foreground">
          {media.evidence.original_filename}
        </p>
        {canEdit ? (
          <div className="flex items-center gap-1">
            <Button
              size="icon"
              variant="ghost"
              className="size-7"
              aria-label="Move image earlier"
              onClick={onMoveEarlier}
            >
              <ArrowUp className="size-3" />
            </Button>
            <Button
              size="icon"
              variant="ghost"
              className="size-7"
              aria-label="Move image later"
              onClick={onMoveLater}
            >
              <ArrowDown className="size-3" />
            </Button>
            {!media.is_cover ? (
              <Button
                size="sm"
                variant="ghost"
                className="h-7 text-[10px]"
                onClick={() => void update({ is_cover: true })}
              >
                Make cover
              </Button>
            ) : null}
            <Button
              size="icon"
              variant="ghost"
              className="ml-auto size-7 text-destructive"
              aria-label="Remove image from Dossier"
              onClick={async () => {
                await dossiersAPI.deleteMedia(dossier.id, media.id)
                refresh()
              }}
            >
              <Trash2 className="size-3" />
            </Button>
          </div>
        ) : null}
        <div className="grid grid-cols-2 gap-2">
          <label className="text-[9px] text-muted-foreground">
            Horizontal focus
            <input
              type="range"
              min="0"
              max="1"
              step=".05"
              defaultValue={media.focal_x ?? 0.5}
              disabled={!canEdit}
              onChange={(event) =>
                void update({ focal_x: Number(event.target.value) })
              }
              className="block w-full"
            />
          </label>
          <label className="text-[9px] text-muted-foreground">
            Vertical focus
            <input
              type="range"
              min="0"
              max="1"
              step=".05"
              defaultValue={media.focal_y ?? 0.5}
              disabled={!canEdit}
              onChange={(event) =>
                void update({ focal_y: Number(event.target.value) })
              }
              className="block w-full"
            />
          </label>
        </div>
      </div>
    </article>
  )
}

export function DossierDetailSheet({
  caseId,
  dossierId,
  open,
  onOpenChange,
  canEdit,
}: {
  caseId: string
  dossierId?: string | null
  open: boolean
  onOpenChange: (open: boolean) => void
  canEdit: boolean
}) {
  const query = useDossier(dossierId)
  const dossier = query.data
  const [mediaOpen, setMediaOpen] = useState(false)
  const [assessmentOpen, setAssessmentOpen] = useState(false)
  const [interviewOpen, setInterviewOpen] = useState(false)
  const [linkOpen, setLinkOpen] = useState(false)
  const [viewerDoc, setViewerDoc] = useState<{
    url: string
    name: string
    page?: number
    time?: number
  } | null>(null)
  const openDocument = async (filename: string, page?: number) => {
    try {
      const result = await evidenceAPI.findByFilename(filename, caseId)
      if (!result.found || !result.evidence_id) {
        toast.error("Source file not found")
        return
      }
      setViewerDoc({
        url: evidenceAPI.getFileUrl(result.evidence_id),
        name: filename,
        page,
      })
    } catch {
      toast.error("Failed to load source file")
    }
  }
  const refresh = () => void query.refetch()
  const moveMedia = async (from: number, to: number) => {
    if (!dossier?.media || to < 0 || to >= dossier.media.length) return
    const ordered = [...dossier.media]
    const [moved] = ordered.splice(from, 1)
    ordered.splice(to, 0, moved)
    try {
      await dossiersAPI.reorderMedia(
        dossier.id,
        ordered.map((item) => item.id)
      )
      refresh()
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Could not reorder gallery"
      )
    }
  }
  const update = useDossierMutation(
    caseId,
    dossierId ?? "",
    (input: Parameters<typeof dossiersAPI.update>[1]) =>
      dossiersAPI.update(dossierId!, input)
  )
  const cover = useMemo(
    () => dossier?.media?.find((item) => item.is_cover),
    [dossier?.media]
  )
  const archive = async () => {
    if (!dossier) return
    try {
      if (dossier.archived_at) await dossiersAPI.restore(dossier.id)
      else await dossiersAPI.archive(dossier.id)
      toast.success(
        dossier.archived_at ? "Dossier restored" : "Dossier archived"
      )
      refresh()
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Could not update Dossier"
      )
    }
  }
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full overflow-y-auto p-0 sm:max-w-3xl">
        <SheetTitle className="sr-only">
          {dossier ? `${dossier.display_name} Dossier` : "Dossier details"}
        </SheetTitle>
        <SheetDescription className="sr-only">
          Investigator-curated subject casework, evidence media, assessments,
          and interviews.
        </SheetDescription>
        {query.isLoading || !dossier ? (
          <div className="flex h-full items-center justify-center">
            <LoadingSpinner />
          </div>
        ) : (
          <>
            <header className="relative min-h-56 overflow-hidden border-b border-border bg-slate-950 text-white">
              {cover ? (
                <EvidenceImage
                  url={cover.evidence.file_url}
                  alt={cover.caption || dossier.display_name}
                  focalX={cover.focal_x}
                  focalY={cover.focal_y}
                  className="absolute inset-0 size-full opacity-55"
                />
              ) : (
                <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_20%,rgba(56,189,248,.16),transparent_45%),linear-gradient(135deg,#172033,#090d16)]" />
              )}
              <div className="absolute inset-0 bg-gradient-to-t from-slate-950 via-slate-950/50 to-transparent" />
              <div className="relative flex min-h-56 flex-col justify-end p-5">
                <div className="mb-2 flex flex-wrap gap-1.5">
                  {dossier.roles.map((role) => (
                    <Badge
                      key={role.id}
                      className="border-white/15 bg-white/10 text-white"
                    >
                      {role.name}
                    </Badge>
                  ))}
                  {dossier.linkage_state === "linked" ? (
                    <Badge className="border-emerald-300/30 bg-emerald-400/15 text-emerald-100">
                      <GitBranch className="size-3" /> Graph linked
                    </Badge>
                  ) : (
                    <Badge className="border-amber-300/30 bg-amber-400/15 text-amber-100">
                      <Link2Off className="size-3" />{" "}
                      {dossier.graph_entity_deleted
                        ? "Entity deleted"
                        : "Unlinked"}
                    </Badge>
                  )}
                  {dossier.needs_link_review ? (
                    <Badge className="bg-red-500/20 text-red-100">
                      Link review required
                    </Badge>
                  ) : null}
                </div>
                <div className="flex items-end justify-between gap-4">
                  <div className="min-w-0">
                    <p className="mb-1 text-xs text-white/60">
                      {dossier.dossier_type} dossier
                    </p>
                    <h2 className="truncate font-display text-2xl font-semibold">
                      {dossier.display_name}
                    </h2>
                    {dossier.importance ? (
                      <p className="mt-1 text-sm text-white/75">
                        {dossier.importance}
                      </p>
                    ) : null}
                  </div>
                  {canEdit ? (
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button
                          size="icon"
                          variant="secondary"
                          aria-label="Dossier actions"
                        >
                          <MoreHorizontal className="size-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        {!dossier.canonical_entity_key ? (
                          <DropdownMenuItem onClick={() => setLinkOpen(true)}>
                            <GitBranch className="size-4" /> Link graph entity
                          </DropdownMenuItem>
                        ) : null}
                        <DropdownMenuItem onClick={() => void archive()}>
                          <Archive className="size-4" />{" "}
                          {dossier.archived_at
                            ? "Restore Dossier"
                            : "Archive Dossier"}
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  ) : null}
                </div>
              </div>
            </header>
            <Tabs defaultValue="brief" className="min-h-0">
              <div className="sticky top-0 z-10 border-b border-border bg-background/95 px-5 backdrop-blur">
                <TabsList variant="line" className="h-11">
                  <TabsTrigger value="brief">Brief</TabsTrigger>
                  <TabsTrigger value="media">
                    Media{" "}
                    {(dossier.media?.length ?? 0) > 0
                      ? `(${dossier.media?.length})`
                      : ""}
                  </TabsTrigger>
                  <TabsTrigger value="assessments">Assessments</TabsTrigger>
                  <TabsTrigger value="interviews">Interviews</TabsTrigger>
                </TabsList>
              </div>
              <TabsContent value="brief" className="space-y-6 p-5">
                <section>
                  <div className="mb-2 flex items-center gap-2">
                    <FileText className="size-4 text-muted-foreground" />
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                      Investigator brief
                    </h3>
                  </div>
                  <Textarea
                    defaultValue={dossier.summary ?? ""}
                    disabled={!canEdit}
                    rows={7}
                    placeholder="No investigator summary yet."
                    onBlur={(event) => {
                      if (event.target.value !== (dossier.summary ?? ""))
                        update.mutate({ summary: event.target.value })
                    }}
                  />
                </section>
                {dossier.canonical_identity ? (
                  <section className="rounded-xl border border-border bg-muted/20 p-4">
                    <div className="mb-3 flex items-center gap-2">
                      <GitBranch className="size-4 text-brand-600" />
                      <h3 className="text-sm font-semibold">
                        Canonical graph identity
                      </h3>
                    </div>
                    <MarkdownSummary
                      content={
                        dossier.canonical_identity.summary ||
                        "No graph summary available."
                      }
                      onOpenFile={openDocument}
                    />
                    {Array.isArray(dossier.canonical_identity.verified_facts) &&
                    dossier.canonical_identity.verified_facts.length ? (
                      <p className="mt-3 text-[11px] text-muted-foreground">
                        {dossier.canonical_identity.verified_facts.length}{" "}
                        source-grounded fact
                        {dossier.canonical_identity.verified_facts.length === 1
                          ? ""
                          : "s"}{" "}
                        available in Graph
                      </p>
                    ) : null}
                  </section>
                ) : (
                  <section className="rounded-xl border border-dashed border-amber-300 bg-amber-50/50 p-4 dark:bg-amber-500/5">
                    <div className="flex gap-3">
                      <Link2Off className="mt-0.5 size-4 text-amber-600" />
                      <div>
                        <h3 className="text-sm font-semibold">
                          This Dossier is not linked to a graph identity
                        </h3>
                        <p className="mt-1 text-xs text-muted-foreground">
                          Authored material is safe here. Link it when a
                          canonical subject becomes available.
                        </p>
                        {canEdit ? (
                          <Button
                            variant="outline"
                            size="sm"
                            className="mt-3"
                            onClick={() => setLinkOpen(true)}
                          >
                            Link graph entity
                          </Button>
                        ) : null}
                      </div>
                    </div>
                  </section>
                )}
                <section>
                  <div className="mb-2 flex items-center gap-2">
                    <Link2 className="size-4 text-muted-foreground" />
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                      Connected casework
                    </h3>
                  </div>
                  {dossier.links?.length ? (
                    <div className="divide-y divide-border rounded-lg border border-border">
                      {dossier.links.map((link) => (
                        <div
                          key={link.id}
                          className="flex items-center gap-3 p-3"
                        >
                          <Badge variant="outline">{link.target_type}</Badge>
                          <span className="min-w-0 flex-1 truncate text-xs">
                            {link.label || link.target_id}
                          </span>
                          {link.relationship_type ? (
                            <span className="text-[10px] text-muted-foreground">
                              {link.relationship_type}
                            </span>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="rounded-lg border border-dashed border-border p-5 text-center text-xs text-muted-foreground">
                      No connected casework yet.
                    </p>
                  )}
                </section>
              </TabsContent>
              <TabsContent value="media" className="p-5">
                <div className="mb-4 flex items-center justify-between">
                  <div>
                    <h3 className="text-sm font-semibold">
                      Evidence-backed gallery
                    </h3>
                    <p className="text-xs text-muted-foreground">
                      Presentation only; original evidence is never modified.
                    </p>
                  </div>
                  {canEdit ? (
                    <Button
                      size="sm"
                      variant="primary"
                      onClick={() => setMediaOpen(true)}
                    >
                      <Camera className="size-4" /> Add image
                    </Button>
                  ) : null}
                </div>
                {dossier.media?.length ? (
                  <div className="grid gap-3 sm:grid-cols-2">
                    {dossier.media.map((item, index) => (
                      <MediaCard
                        key={item.id}
                        dossier={dossier}
                        media={item}
                        canEdit={canEdit}
                        refresh={refresh}
                        onMoveEarlier={() => void moveMedia(index, index - 1)}
                        onMoveLater={() => void moveMedia(index, index + 1)}
                      />
                    ))}
                  </div>
                ) : (
                  <div className="rounded-xl border border-dashed border-border py-14 text-center">
                    <Camera className="mx-auto size-7 text-muted-foreground" />
                    <p className="mt-3 text-sm font-medium">No curated media</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      Attach images already held in Evidence.
                    </p>
                  </div>
                )}
              </TabsContent>
              <TabsContent value="assessments" className="p-5">
                <div className="mb-4 flex items-center justify-between">
                  <div>
                    <h3 className="text-sm font-semibold">
                      Investigator assessments
                    </h3>
                    <p className="text-xs text-muted-foreground">
                      Dated, attributed analysis—not objective identity facts.
                    </p>
                  </div>
                  {canEdit ? (
                    <Button size="sm" onClick={() => setAssessmentOpen(true)}>
                      <Plus className="size-4" /> Assessment
                    </Button>
                  ) : null}
                </div>
                <div className="space-y-3">
                  {dossier.assessments?.map((item) => (
                    <article
                      key={item.id}
                      className="rounded-lg border border-border bg-card p-4"
                    >
                      <div className="flex items-center gap-2">
                        <ShieldCheck className="size-4 text-amber-600" />
                        <Badge variant="amber">{item.category}</Badge>
                        {item.legacy_label ? (
                          <Badge variant="outline">{item.legacy_label}</Badge>
                        ) : null}
                        {item.provenance_type === "ai_assisted" ? (
                          <Badge variant="info">
                            <Sparkles className="size-3" /> AI-assisted ·
                            investigator accepted
                          </Badge>
                        ) : null}
                        <span className="ml-auto text-[10px] text-muted-foreground">
                          {formatDate(item.assessment_date || item.created_at)}
                        </span>
                      </div>
                      <p className="mt-2 whitespace-pre-wrap text-xs leading-relaxed">
                        {item.content}
                      </p>
                      {item.supporting_links.length ? (
                        <div className="mt-3 border-t border-border pt-2 text-[11px] text-muted-foreground">
                          Supported by{" "}
                          {item.supporting_links
                            .map((link) => link.label || link.target_id)
                            .join(", ")}
                        </div>
                      ) : null}
                    </article>
                  ))}
                  {!dossier.assessments?.length ? (
                    <p className="rounded-lg border border-dashed border-border py-10 text-center text-xs text-muted-foreground">
                      No assessments recorded.
                    </p>
                  ) : null}
                </div>
              </TabsContent>
              <TabsContent value="interviews" className="space-y-5 p-5">
                <div className="mb-4 flex items-center justify-between">
                  <div>
                    <h3 className="text-sm font-semibold">
                      Interviews & statements
                    </h3>
                    <p className="text-xs text-muted-foreground">
                      Original transcripts and statements linked to this
                      dossier.
                    </p>
                  </div>
                  {canEdit ? (
                    <Button size="sm" onClick={() => setInterviewOpen(true)}>
                      <Plus className="size-4" /> Interview
                    </Button>
                  ) : null}
                </div>
                <div className="space-y-2">
                  {dossier.interviews?.map((item) => (
                    <article
                      key={item.id}
                      className="rounded-lg border border-border bg-card px-3 py-2.5"
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        <CalendarDays className="size-4 text-muted-foreground" />
                        <span className="text-xs font-semibold">
                          {formatDate(item.interview_date)}
                        </span>
                        {item.participants.length ? (
                          <p className="text-xs text-muted-foreground sm:ml-auto">
                            <UserRound className="mr-1 inline size-3" />{" "}
                            {item.participants
                              .map((p) =>
                                typeof p === "string"
                                  ? p
                                  : String(p.name ?? "Participant")
                              )
                              .join(", ")}
                          </p>
                        ) : null}
                      </div>
                      {item.working_notes ? (
                        <p className="mt-2 whitespace-pre-wrap text-xs leading-relaxed">
                          {item.working_notes}
                        </p>
                      ) : null}
                      {item.evidence_links.length ? (
                        <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1">
                          {item.evidence_links.map((link) => (
                            <button
                              type="button"
                              key={link.id}
                              onClick={() =>
                                setViewerDoc({
                                  url: evidenceAPI.getFileUrl(
                                    link.evidence_file_id
                                  ),
                                  name: link.evidence.original_filename,
                                  page:
                                    typeof link.source_anchor?.page === "number"
                                      ? link.source_anchor.page
                                      : undefined,
                                  time:
                                    typeof link.source_anchor?.start_seconds ===
                                    "number"
                                      ? link.source_anchor.start_seconds
                                      : undefined,
                                })
                              }
                              className="inline-flex min-h-10 items-center gap-1.5 break-all text-left text-xs text-amber-500 underline underline-offset-2 hover:text-amber-400"
                            >
                              <FileText className="size-3" />{" "}
                              {link.evidence.original_filename}
                            </button>
                          ))}
                        </div>
                      ) : null}
                    </article>
                  ))}
                  {!dossier.interviews?.length ? (
                    <p className="rounded-lg border border-dashed border-border py-10 text-center text-xs text-muted-foreground">
                      No interviews or statements recorded.
                    </p>
                  ) : null}
                </div>
                <WorkspaceAIPanel
                  caseId={caseId}
                  targetType="dossier"
                  targetId={dossier.id}
                  canEdit={canEdit}
                  interviews={dossier.interviews ?? []}
                />
              </TabsContent>
            </Tabs>
            <AddMediaDialog
              caseId={caseId}
              dossier={dossier}
              open={mediaOpen}
              onOpenChange={setMediaOpen}
              onSaved={refresh}
            />
            <AssessmentDialog
              caseId={caseId}
              dossier={dossier}
              open={assessmentOpen}
              onOpenChange={setAssessmentOpen}
              onSaved={refresh}
            />
            <InterviewDialog
              caseId={caseId}
              dossier={dossier}
              open={interviewOpen}
              onOpenChange={setInterviewOpen}
              onSaved={refresh}
            />
            <Dialog open={linkOpen} onOpenChange={setLinkOpen}>
              <DialogContent className="max-h-[calc(100dvh-2rem)] overflow-y-auto">
                <DialogHeader>
                  <DialogTitle>Link canonical graph identity</DialogTitle>
                  <DialogDescription>
                    Choose the evidence-derived entity whose current identity
                    this Dossier should use.
                  </DialogDescription>
                </DialogHeader>
                <NotebookEntityPicker
                  caseId={caseId}
                  onAttach={async (link) => {
                    try {
                      await dossiersAPI.link(dossier.id, link.target_id)
                      toast.success("Dossier linked")
                      setLinkOpen(false)
                      refresh()
                    } catch (error) {
                      toast.error(
                        error instanceof Error
                          ? error.message
                          : "Could not link Dossier"
                      )
                    }
                  }}
                />
              </DialogContent>
            </Dialog>
          </>
        )}
      </SheetContent>
      <DocumentViewer
        open={!!viewerDoc}
        onOpenChange={(open) => {
          if (!open) setViewerDoc(null)
        }}
        documentUrl={viewerDoc?.url}
        documentName={viewerDoc?.name}
        initialPage={viewerDoc?.page}
        initialTime={viewerDoc?.time}
      />
    </Sheet>
  )
}
