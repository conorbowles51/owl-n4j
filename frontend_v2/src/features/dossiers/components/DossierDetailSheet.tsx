import { LoadProgress } from "@/features/financial/components/LoadProgress"
import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react"
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
import { useLocation, useNavigate } from "react-router-dom"
import { useUnsavedHistoryGuard } from "@/hooks/use-unsaved-history-guard"
import { PhoneLinkDetail } from "@/features/phones/PhoneLinkDetail"
import { CollectedPhoneExport } from "@/features/phones/CollectedPhoneExport"
import { passageHref } from "@/features/evidence/lib/text-workbench-link"
import { LinkStateNote } from "@/features/phones/LinkStateNote"
import { useLinkChoice, useLinkStates } from "@/features/phones/link-states"
import {
  isPhoneLinkType,
  phoneLinkHref,
  phoneLinkSummary,
} from "@/features/phones/phone-links"
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
import { MarkdownSummary } from "@/components/ui/markdown-summary"
import { DossierSourceViewer } from "./DossierSourceViewer"
import { AddDossierEvidenceDialog } from "./AddDossierEvidenceDialog"
import { DossierInterviewDialog } from "./DossierInterviewDialog"
import { EditDossierDialog } from "./EditDossierDialog"
import { DossierContacts } from "./DossierContacts"
import { formatInterviewDate } from "../interview-date"
import { DossierIcon } from "./DossierIcon"
import { dossierTypeLabel } from "../dossier-type"
import { AddDossierCaseworkDialog } from "./AddDossierCaseworkDialog"
import { DossierBriefEditor } from "./DossierBriefEditor"
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
import { OnThePhonesPanel } from "./OnThePhonesPanel"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Textarea } from "@/components/ui/textarea"
import { NotebookEntityPicker } from "@/features/notebook/components/NotebookEntityPicker"
import {
  dossiersAPI,
  type Dossier,
  type DossierMedia,
  type DossierLink,
  type DossierInterview,
} from "../api"
import { splitParticipants } from "../interview-participants"
import { dossierKeys, useDossier, useDossierMutation } from "../hooks"
import { useQueryClient } from "@tanstack/react-query"
import { RemovedFromDossier } from "./RemovedFromDossier"
import { DossierEvidencePicker } from "./DossierEvidencePicker"
import { EvidenceImage } from "./EvidenceImage"
import { WorkspaceAIPanel } from "@/features/workspace-ai/components/WorkspaceAIPanel"
import { AddToTheory } from "@/features/theory/AddToTheory"

const CaseworkDetailSheet = lazy(() =>
  import("@/features/workspace/components/CaseworkDetailSheet").then(
    (module) => ({ default: module.CaseworkDetailSheet })
  )
)

/** Links whose phone records a dossier's phone export draws (records, collected selections, conversations). */
const PHONE_EXPORTABLE = ["phone_record", "phone_selection", "phone_thread"]

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

function MediaCard({
  dossier,
  media,
  canEdit,
  refresh,
  onMoveEarlier,
  onMoveLater,
  onOpen,
}: {
  dossier: Dossier
  media: DossierMedia
  canEdit: boolean
  refresh: () => void
  onMoveEarlier: () => void
  onMoveLater: () => void
  onOpen: () => void
}) {
  const [caption, setCaption] = useState(media.caption ?? "")
  const [confirmRemove, setConfirmRemove] = useState(false)
  const remove = useDossierMutation(dossier.case_id, dossier.id, () =>
    dossiersAPI.deleteMedia(dossier.id, media.id)
  )
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
      <button
        type="button"
        onClick={onOpen}
        aria-label={`Open ${media.evidence.original_filename}`}
        className="relative block aspect-[4/3] w-full"
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
      </button>
      <div className="space-y-2 p-3">
        <Input
          className="h-7 border-transparent bg-transparent px-0 text-xs font-medium focus:border-border focus:px-2"
          value={caption}
          disabled={!canEdit}
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
              onClick={() => setConfirmRemove(true)}
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
      <Dialog
        open={confirmRemove}
        onOpenChange={(value) => {
          if (!remove.isPending) setConfirmRemove(value)
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Remove image from dossier?</DialogTitle>
            <DialogDescription>
              {media.evidence.original_filename} will leave this gallery. The
              original evidence stays saved and you can put the image back from
              Removed from this dossier.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="ghost"
              disabled={remove.isPending}
              onClick={() => setConfirmRemove(false)}
            >
              Cancel
            </Button>
            <Button
              disabled={remove.isPending}
              onClick={async () => {
                try {
                  await remove.mutateAsync(undefined)
                  setConfirmRemove(false)
                  refresh()
                } catch {
                  toast.error("Could not remove the image. Try again.")
                }
              }}
            >
              {remove.isPending ? "Removing…" : "Remove image"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </article>
  )
}

export function DossierDetailSheet({
  caseId,
  dossierId,
  open,
  onOpenChange,
  canEdit,
  onBeforeNavigate,
}: {
  caseId: string
  dossierId?: string | null
  open: boolean
  onOpenChange: (open: boolean) => void
  canEdit: boolean
  onBeforeNavigate?: () => boolean
}) {
  const query = useDossier(dossierId)
  const dossier = query.data
  const linkStates = useLinkStates(
    caseId,
    "dossier",
    dossierId ?? undefined,
    !!dossier
  )
  const linkChoice = useLinkChoice(
    caseId,
    "dossier",
    dossierId ?? undefined,
    () => void query.refetch()
  )
  const [briefDirty, setBriefDirty] = useState(false)
  useUnsavedHistoryGuard(open && briefDirty, "Leave this dossier and discard your unsaved brief?")
  const [discardOpen, setDiscardOpen] = useState(false)
  const [mediaOpen, setMediaOpen] = useState(false)
  const [detailsOpen, setDetailsOpen] = useState(false)
  const [archiveBusy, setArchiveBusy] = useState(false)
  const [assessmentOpen, setAssessmentOpen] = useState(false)
  const [interviewOpen, setInterviewOpen] = useState(false)
  const [interviewToEdit, setInterviewToEdit] =
    useState<DossierInterview | null>(null)
  const [interviewToRemove, setInterviewToRemove] =
    useState<DossierInterview | null>(null)
  const [linkOpen, setLinkOpen] = useState(false)
  const [addEvidenceOpen, setAddEvidenceOpen] = useState(false)
  const [addCaseworkOpen, setAddCaseworkOpen] = useState(false)
  const collectedRef = useRef<HTMLElement>(null)
  const [entryId, setEntryId] = useState<string | null>(null)
  const [linkedDossierId, setLinkedDossierId] = useState<string | null>(null)
  const [removeLink, setRemoveLink] = useState<DossierLink | null>(null)
  const navigate = useNavigate()
  const location = useLocation()
  const allowNavigation = () => {
    if (
      briefDirty &&
      !window.confirm("Leave this dossier and discard your unsaved brief?")
    )
      return false
    return onBeforeNavigate?.() ?? true
  }
  const navigateTo = (href: string) => {
    if (allowNavigation()) navigate(href)
  }
  const removeInterview = useDossierMutation(
    caseId,
    dossierId ?? "",
    (id: string) => dossiersAPI.deleteInterview(dossierId!, id)
  )
  const removeEvidence = useDossierMutation(
    caseId,
    dossierId ?? "",
    (id: string) => dossiersAPI.removeEvidence(dossierId!, id)
  )
  const removeOtherLink = useDossierMutation(
    caseId,
    dossierId ?? "",
    (linkId: string) => dossiersAPI.removeLink(dossierId!, linkId)
  )
  const unlinking = removeEvidence.isPending || removeOtherLink.isPending
  const unlinkingEvidence = removeLink?.target_type === "evidence"
  const [viewerDoc, setViewerDoc] = useState<{
    evidenceId: string
    url: string
    name: string
    page?: number
    time?: number
  } | null>(null)
  const openLinkedItem = (
    link: Pick<
      DossierLink,
      "target_type" | "target_id" | "label" | "source_anchor"
    >
  ) => {
    if (link.target_type === "evidence")
      setViewerDoc({
        evidenceId: link.target_id,
        url: evidenceAPI.getFileUrl(link.target_id),
        name: link.label || "Source evidence",
        page:
          typeof link.source_anchor?.page === "number"
            ? link.source_anchor.page
            : undefined,
        time:
          typeof link.source_anchor?.start_seconds === "number"
            ? link.source_anchor.start_seconds
            : undefined,
      })
    else if (link.target_type === "evidence_passage")
      navigateTo(passageHref(caseId, link.target_id, link.source_anchor))
    else if (isPhoneLinkType(link.target_type)) {
      const href = phoneLinkHref(caseId, link)
      if (href) navigateTo(href)
    } else if (["task", "deadline"].includes(link.target_type))
      navigateTo(
        `/cases/${caseId}/workspace?view=work&item=${encodeURIComponent(link.target_id)}`
      )
    else if (link.target_type === "entry") setEntryId(link.target_id)
    else if (link.target_type === "dossier" && link.target_id !== dossierId)
      setLinkedDossierId(link.target_id)
  }
  const renderSourceLink = (link: DossierLink) => (
    <span key={link.id} className="inline-flex flex-col">
      <button
        type="button"
        className="min-h-10 break-all text-left text-xs text-amber-600 underline underline-offset-2 hover:text-amber-700 dark:text-amber-400"
        onClick={() => openLinkedItem(link)}
      >
        {link.label ||
          (isPhoneLinkType(link.target_type)
            ? phoneLinkSummary(link).kind
            : "Open source evidence")}
        {isPhoneLinkType(link.target_type) && <PhoneLinkDetail link={link} />}
      </button>
      <LinkStateNote
        caseId={caseId}
        state={linkStates[link.id]}
        busy={linkChoice.isPending}
        onChoose={(state, choice) => linkChoice.mutateAsync({ state, choice })}
      />
    </span>
  )
  const queryClient = useQueryClient()
  const refresh = () => {
    void query.refetch()
    void queryClient.invalidateQueries({
      queryKey: dossierKeys.removed(dossierId ?? ""),
    })
    void queryClient.invalidateQueries({ queryKey: dossierKeys.lists(caseId) })
    void queryClient.invalidateQueries({
      queryKey: ["dossiers", "picker", caseId],
    })
    void queryClient.invalidateQueries({
      queryKey: ["workspace", caseId, "overview"],
    })
    void queryClient.invalidateQueries({ queryKey: ["significant", caseId] })
  }
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
  const cover = useMemo(
    () => dossier?.media?.find((item) => item.is_cover),
    [dossier?.media]
  )
  const archive = async () => {
    if (!dossier || archiveBusy) return
    setArchiveBusy(true)
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
    } finally {
      setArchiveBusy(false)
    }
  }
  return (
    <Sheet
      open={open}
      onOpenChange={(value) => {
        if (!value && briefDirty) setDiscardOpen(true)
        else onOpenChange(value)
      }}
    >
      <SheetContent
        guardTypedContent={false}
        className="w-full gap-0 overflow-y-auto bg-background p-0 sm:max-w-3xl"
        onClickCapture={(event) => {
          const anchor =
            event.target instanceof Element
              ? event.target.closest("a[href]")
              : null
          const href = anchor?.getAttribute("href")
          if (
            href?.startsWith("/") &&
            anchor?.getAttribute("target") !== "_blank" &&
            href !== location.pathname + location.search &&
            !allowNavigation()
          ) {
            event.preventDefault()
            event.stopPropagation()
          }
        }}
      >
        <SheetTitle className="sr-only">
          {dossier ? `${dossier.display_name} Dossier` : "Dossier details"}
        </SheetTitle>
        <SheetDescription className="sr-only">
          Investigator-curated subject casework, evidence media, assessments,
          and interviews.
        </SheetDescription>
        {query.isError ? (
          <div className="space-y-3 p-8 text-center" role="alert">
            <p>
              This dossier could not be loaded. Your saved work has not changed.
            </p>
            <Button variant="outline" onClick={refresh}>
              Retry dossier
            </Button>
          </div>
        ) : query.isLoading || !dossier ? (
          <div className="flex h-full items-center justify-center">
            <LoadProgress caseId={caseId} page="case/dossier" />
          </div>
        ) : (
          <>
            <header className="shrink-0 border-b border-border/75 px-5 pb-6 pt-10 sm:px-8">
              <div className="flex items-start gap-4">
                {cover ? (
                  <EvidenceImage
                    url={cover.evidence.file_url}
                    alt={cover.caption || dossier.display_name}
                    focalX={cover.focal_x}
                    focalY={cover.focal_y}
                    className="size-16 shrink-0 rounded-xl"
                  />
                ) : (
                  <DossierIcon
                    type={dossier.dossier_type}
                    className="size-12"
                  />
                )}
                <div className="min-w-0 flex-1">
                  <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-[.16em] text-muted-foreground">
                    {dossierTypeLabel(dossier.dossier_type)} dossier
                  </p>
                  <h2 className="break-words font-display text-2xl font-semibold tracking-tight">
                    {dossier.display_name}
                  </h2>
                  {dossier.importance && (
                    <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                      {dossier.importance}
                    </p>
                  )}
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {dossier.roles.map((role) => (
                      <Badge key={role.id} variant="outline">
                        {role.name}
                      </Badge>
                    ))}
                    {dossier.archived_at && (
                      <Badge variant="outline">
                        <Archive className="size-3" /> Archived
                      </Badge>
                    )}
                    <span className="inline-flex items-center gap-1.5 text-[11px] text-muted-foreground">
                      {dossier.linkage_state === "linked" ? (
                        <>
                          <GitBranch className="size-3" /> Graph linked
                        </>
                      ) : (
                        <>
                          <Link2Off className="size-3" />
                          {dossier.graph_entity_deleted
                            ? "Graph entity deleted"
                            : "Unlinked"}
                        </>
                      )}
                    </span>
                    {dossier.needs_link_review && (
                      <Badge variant="warning">Link review required</Badge>
                    )}
                  </div>
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
                      <DropdownMenuItem onClick={() => setDetailsOpen(true)}>
                        Edit dossier details
                      </DropdownMenuItem>
                      {!dossier.canonical_entity_key ? (
                        <DropdownMenuItem onClick={() => setLinkOpen(true)}>
                          <GitBranch className="size-4" /> Link graph entity
                        </DropdownMenuItem>
                      ) : null}
                      <DropdownMenuItem
                        disabled={archiveBusy}
                        onClick={() => void archive()}
                      >
                        <Archive className="size-4" />{" "}
                        {dossier.archived_at
                          ? "Restore Dossier"
                          : "Archive Dossier"}
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                ) : null}
              </div>
            </header>
            <Tabs defaultValue="brief" className="shrink-0">
              <div className="sticky top-0 z-10 overflow-x-auto border-b border-border/75 bg-background/95 px-5 backdrop-blur sm:px-8">
                <TabsList
                  variant="line"
                  className="h-12 w-max min-w-full justify-start gap-3"
                >
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
              <TabsContent
                value="brief"
                forceMount
                className="space-y-8 px-5 py-6 data-[state=inactive]:hidden sm:px-8"
              >
                <section>
                  <div className="mb-2 flex items-center gap-2">
                    <FileText className="size-4 text-muted-foreground" />
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                      Investigator brief
                    </h3>
                  </div>
                  <DossierBriefEditor
                    key={dossier.id}
                    dossier={dossier}
                    canEdit={canEdit}
                    onDirtyChange={setBriefDirty}
                  />
                </section>
                <section
                  ref={collectedRef}
                  tabIndex={-1}
                  className="scroll-mt-20 border-t border-border/75 pt-6 outline-none"
                >
                  <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                    <h3 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                      <Link2 className="size-4" /> Collected work
                    </h3>
                    {dossier.links?.some((link) =>
                      PHONE_EXPORTABLE.includes(link.target_type)
                    ) && (
                      <CollectedPhoneExport
                        caseId={caseId}
                        source="dossier"
                        id={dossier.id}
                      />
                    )}
                    {canEdit && (
                      <div className="flex flex-wrap gap-1">
                        <Button
                          size="sm"
                          variant="ghost"
                          className="min-h-10"
                          onClick={() => setAddCaseworkOpen(true)}
                        >
                          <Plus className="size-3.5" /> Add casework
                        </Button>
                        <Button
                          size="sm"
                          className="min-h-10"
                          variant="outline"
                          onClick={() => setAddEvidenceOpen(true)}
                        >
                          <Plus className="size-3.5" /> Add evidence
                        </Button>
                      </div>
                    )}
                  </div>
                  {dossier.links?.length ? (
                    <div className="divide-y divide-border/60">
                      {dossier.links.map((link) => (
                        <div
                          key={link.id}
                          className="flex flex-wrap items-center gap-3 py-3"
                        >
                          <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                            {link.target_type === "entry"
                              ? "Casework"
                              : link.target_type.replaceAll("_", " ")}
                          </span>
                          {link.target_type === "evidence_passage" ? (
                            <span className="min-w-0 flex-1 break-all text-xs">
                              <button
                                type="button"
                                className="min-h-10 text-left font-medium underline underline-offset-2 hover:text-amber-600"
                                onClick={() => openLinkedItem(link)}
                              >
                                {link.label || "Open quote"}
                              </button>
                              <LinkStateNote
                                caseId={caseId}
                                state={linkStates[link.id]}
                              />
                            </span>
                          ) : [
                              "evidence",
                              "entry",
                              "dossier",
                              "task",
                              "deadline",
                            ].includes(link.target_type) ||
                            isPhoneLinkType(link.target_type) ? (
                            <button
                              type="button"
                              className="min-h-10 min-w-0 flex-1 break-all text-left text-xs font-medium underline underline-offset-2 hover:text-amber-600"
                              onClick={() => openLinkedItem(link)}
                            >
                              {link.label || `Open ${link.target_type}`}
                            </button>
                          ) : (
                            <span className="min-w-0 flex-1 break-all text-xs">
                              {link.label || link.target_id}
                              <LinkStateNote
                                caseId={caseId}
                                state={linkStates[link.id]}
                                busy={linkChoice.isPending}
                                onChoose={(state, choice) =>
                                  linkChoice.mutateAsync({ state, choice })
                                }
                              />
                            </span>
                          )}
                          {link.target_type === "phone_selection" && (
                            <CollectedPhoneExport
                              caseId={caseId}
                              source="collection"
                              id={link.target_id}
                              label="Export"
                            />
                          )}
                          {canEdit && (
                            <Button
                              variant="ghost"
                              size="icon"
                              aria-label={`Unlink ${link.label || (link.target_type === "evidence" ? "evidence" : "this item")}`}
                              onClick={() => setRemoveLink(link)}
                            >
                              <Trash2 className="size-3.5" />
                            </Button>
                          )}
                          {link.relationship_type ? (
                            <span className="text-[10px] text-muted-foreground">
                              {link.relationship_type}
                            </span>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  ) : !dossier.incoming_casework?.length ? (
                    <p className="py-4 text-sm leading-relaxed text-muted-foreground">
                      Collect the evidence, notes and findings relevant to this
                      subject. Originals remain in their working views.
                    </p>
                  ) : null}
                  {!!dossier.incoming_casework?.length && (
                    <div className="mt-4 border-t border-border/60 pt-4">
                      <p className="text-xs font-medium">
                        Linked from casework
                      </p>
                      <p className="mt-1 text-xs text-muted-foreground">
                        These references are managed in the original note,
                        finding or theory.
                      </p>
                      <div className="mt-2 divide-y divide-border/60">
                        {dossier.incoming_casework.map((item) => (
                          <button
                            type="button"
                            key={item.id}
                            onClick={() => setEntryId(item.id)}
                            className="flex min-h-12 w-full items-center gap-3 py-3 text-left hover:text-brand-600"
                          >
                            <span className="text-[10px] capitalize text-muted-foreground">
                              {item.entry_type}
                            </span>
                            <span className="min-w-0 flex-1 break-words text-sm font-medium">
                              {item.title}
                            </span>
                            <span className="text-[11px] text-muted-foreground">
                              {item.relationship === "unclassified"
                                ? ""
                                : item.relationship}
                            </span>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </section>
                <DossierContacts
                  dossier={dossier}
                  canEdit={canEdit}
                  onOpenSource={(id) =>
                    openLinkedItem({
                      target_type: "evidence",
                      target_id: id,
                      label: "Contact source",
                      source_anchor: {},
                    })
                  }
                />
                <OnThePhonesPanel
                  caseId={caseId}
                  dossierId={dossier.id}
                  canEdit={canEdit}
                />
                <section className="space-y-3">
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    Accepted summaries & comparisons
                  </h3>
                  {(dossier.assessments ?? [])
                    .filter((item) =>
                      ["statement_summary", "statement_comparison"].includes(
                        item.category
                      )
                    )
                    .map((item) => (
                      <article
                        key={item.id}
                        className="space-y-3 border-l-2 border-brand-500/30 pl-4"
                      >
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge variant="outline">
                            {item.category === "statement_summary"
                              ? "Statement summary"
                              : "Statement comparison"}
                          </Badge>
                          <span className="text-[11px] text-muted-foreground">
                            {item.read_by
                              ? item.read_by
                              : item.provenance_type === "ai_assisted"
                                ? "AI-assisted · investigator accepted"
                                : "Investigator recorded"}{" "}
                            · {formatDate(item.created_at)}
                          </span>
                        </div>
                        <MarkdownSummary content={item.content} />
                        <div className="flex flex-wrap gap-x-3">
                          {item.supporting_links.map(renderSourceLink)}
                        </div>
                      </article>
                    ))}
                  {!(dossier.assessments ?? []).some((item) =>
                    ["statement_summary", "statement_comparison"].includes(
                      item.category
                    )
                  ) && (
                    <p className="text-xs text-muted-foreground">
                      Accepted interview summaries and statement comparisons
                      will appear here. Review proposals in Interviews.
                    </p>
                  )}
                </section>
                {(dossier.interviews?.length ?? 0) > 0 && (
                  <section className="space-y-3">
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                      Interviews at a glance
                    </h3>
                    <div className="divide-y rounded-lg border">
                      {dossier.interviews?.map((item) => (
                        <article key={item.id} className="space-y-2 p-3">
                          <p className="text-xs font-semibold">
                            {formatInterviewDate(
                              item.date_value ?? item.interview_date
                            )}
                          </p>
                          <p className="whitespace-pre-wrap text-xs text-muted-foreground">
                            {item.working_notes || "No working notes recorded."}
                          </p>
                          <div className="flex flex-wrap gap-x-3">
                            {item.evidence_links.map((link) =>
                              renderSourceLink({
                                id: link.id,
                                target_type: link.evidence_file_id
                                  ? "evidence"
                                  : (link.target_type ?? "evidence"),
                                target_id:
                                  link.evidence_file_id ?? link.target_id ?? "",
                                label: link.evidence?.original_filename ?? null,
                                source_anchor: link.source_anchor,
                              })
                            )}
                          </div>
                        </article>
                      ))}
                    </div>
                  </section>
                )}
                {dossier.canonical_identity ? (
                  <section className="border-t border-border/75 pt-6">
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
                  <section className="border-t border-border/75 pt-6">
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
                        onOpen={() =>
                          openLinkedItem({
                            target_type: "evidence",
                            target_id: item.evidence_file_id,
                            label: item.evidence.original_filename,
                            source_anchor: item.source_anchor,
                          })
                        }
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
                      className="border-b border-border/75 py-5"
                    >
                      <div className="flex items-center gap-2">
                        <ShieldCheck className="size-4 text-amber-600" />
                        <Badge variant="amber">{item.category}</Badge>
                        {item.legacy_label ? (
                          <Badge variant="outline">{item.legacy_label}</Badge>
                        ) : null}
                        {item.provenance_type === "ai_assisted" ? (
                          <Badge variant="info">
                            <Sparkles className="size-3" />{" "}
                            {item.read_by ??
                              "AI-assisted · investigator accepted"}
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
                          <div className="flex flex-wrap gap-x-3">
                            {item.supporting_links.map(renderSourceLink)}
                          </div>
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
                    <Button
                      size="sm"
                      onClick={() => {
                        setInterviewToEdit(null)
                        setInterviewOpen(true)
                      }}
                    >
                      <Plus className="size-4" /> Interview
                    </Button>
                  ) : null}
                </div>
                <div className="space-y-2">
                  {dossier.interviews?.map((item) => (
                    <article
                      key={item.id}
                      className="border-b border-border/75 py-5"
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        <CalendarDays className="size-4 text-muted-foreground" />
                        <AddToTheory
                          caseId={caseId}
                          surface="interview"
                          label="Theory…"
                          items={[
                            {
                              target_type: "interview",
                              target_id: item.id,
                              target_label: `Interview with ${dossier.display_name}, ${formatInterviewDate(item.date_value ?? item.interview_date)}`,
                            },
                          ]}
                        />
                        {canEdit && (
                          <div className="ml-auto flex gap-1">
                            <Button
                              size="sm"
                              variant="ghost"
                              aria-label={`Edit interview ${formatInterviewDate(item.date_value ?? item.interview_date)}`}
                              onClick={() => {
                                setInterviewToEdit(item)
                                setInterviewOpen(true)
                              }}
                            >
                              Edit
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              aria-label={`Remove interview ${formatInterviewDate(item.date_value ?? item.interview_date)}`}
                              onClick={() => setInterviewToRemove(item)}
                            >
                              Remove
                            </Button>
                          </div>
                        )}
                        <span className="text-xs font-semibold">
                          {formatInterviewDate(
                            item.date_value ?? item.interview_date
                          )}
                        </span>
                        {splitParticipants(item.participants).names.length ? (
                          <p className="text-xs text-muted-foreground sm:ml-auto">
                            <UserRound className="mr-1 inline size-3" />{" "}
                            {splitParticipants(item.participants).names.join(
                              ", "
                            )}
                          </p>
                        ) : null}
                      </div>
                      {splitParticipants(item.participants).interviewedBy ? (
                        <p className="mt-1 text-xs text-muted-foreground">
                          Interviewed by:{" "}
                          {splitParticipants(item.participants).interviewedBy}
                        </p>
                      ) : null}
                      {item.working_notes ? (
                        <InterviewNotes text={item.working_notes} />
                      ) : null}
                      {item.evidence_links.length ? (
                        <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1">
                          {item.evidence_links.map((link) =>
                            !link.evidence_file_id ? (
                              renderSourceLink({
                                id: link.id,
                                target_type: link.target_type ?? "",
                                target_id: link.target_id ?? "",
                                label: null,
                                source_anchor: link.source_anchor,
                              })
                            ) : (
                              <button
                                type="button"
                                key={link.id}
                                onClick={() =>
                                  setViewerDoc({
                                    evidenceId: link.evidence_file_id!,
                                    url: evidenceAPI.getFileUrl(
                                      link.evidence_file_id!
                                    ),
                                    name:
                                      link.evidence?.original_filename ??
                                      "Evidence file",
                                    page:
                                      typeof link.source_anchor?.page ===
                                      "number"
                                        ? link.source_anchor.page
                                        : undefined,
                                    time:
                                      typeof link.source_anchor
                                        ?.start_seconds === "number"
                                        ? link.source_anchor.start_seconds
                                        : undefined,
                                  })
                                }
                                className="inline-flex min-h-10 items-center gap-1.5 break-all text-left text-xs text-amber-500 underline underline-offset-2 hover:text-amber-400"
                              >
                                <FileText className="size-3" />{" "}
                                {link.evidence?.original_filename ??
                                  "Evidence file"}
                              </button>
                            )
                          )}
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
            <RemovedFromDossier
              caseId={caseId}
              dossierId={dossier.id}
              canEdit={canEdit}
            />
            {detailsOpen && (
              <EditDossierDialog
                dossier={dossier}
                onClose={() => setDetailsOpen(false)}
              />
            )}
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
            {interviewOpen && (
              <DossierInterviewDialog
                key={interviewToEdit?.id ?? "new"}
                dossier={dossier}
                interview={interviewToEdit}
                onClose={() => setInterviewOpen(false)}
              />
            )}
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
                  resultLimit={100}
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
      <Dialog open={discardOpen} onOpenChange={setDiscardOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Unsaved brief</DialogTitle>
            <DialogDescription>
              Your brief has unsaved changes. Return to the Brief to save them,
              or discard them and close this dossier.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDiscardOpen(false)}>
              Keep editing
            </Button>
            <Button
              onClick={() => {
                setDiscardOpen(false)
                setBriefDirty(false)
                onOpenChange(false)
              }}
            >
              Discard and close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <DossierSourceViewer
        caseId={caseId}
        source={viewerDoc}
        onClose={() => setViewerDoc(null)}
      />
      {entryId && (
        <Suspense fallback={<div role="status">Loading linked casework…</div>}>
          <CaseworkDetailSheet
            caseId={caseId}
            entryId={entryId}
            open
            canEdit={canEdit}
            onOpenChange={(value) => {
              if (!value) setEntryId(null)
            }}
            onOpenEntry={setEntryId}
            onOpenEvidence={(id, name, anchor) =>
              openLinkedItem({
                target_type: "evidence",
                target_id: id,
                label: name,
                source_anchor: anchor,
              })
            }
            onOpenDossier={setLinkedDossierId}
            onBeforeNavigate={allowNavigation}
          />
        </Suspense>
      )}
      {linkedDossierId && (
        <DossierDetailSheet
          key={linkedDossierId}
          caseId={caseId}
          dossierId={linkedDossierId}
          onBeforeNavigate={allowNavigation}
          open
          canEdit={canEdit}
          onOpenChange={(value) => {
            if (!value) setLinkedDossierId(null)
          }}
        />
      )}
      {dossier && addCaseworkOpen && (
        <AddDossierCaseworkDialog
          dossier={dossier}
          onClose={() => setAddCaseworkOpen(false)}
          onSaved={() => {
            collectedRef.current?.scrollIntoView({ block: "start" })
            collectedRef.current?.focus()
          }}
        />
      )}
      {dossier && addEvidenceOpen && (
        <AddDossierEvidenceDialog
          dossier={dossier}
          onClose={() => setAddEvidenceOpen(false)}
        />
      )}
      <Dialog
        open={Boolean(interviewToRemove)}
        onOpenChange={(value) => {
          if (!value && !removeInterview.isPending) setInterviewToRemove(null)
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Remove interview from dossier?</DialogTitle>
            <DialogDescription>
              The interview entry and its working notes will be removed. A copy
              is kept: put it back from Removed from this dossier. Original
              evidence files and accepted assessments remain saved.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="ghost"
              disabled={removeInterview.isPending}
              onClick={() => setInterviewToRemove(null)}
            >
              Cancel
            </Button>
            <Button
              disabled={removeInterview.isPending}
              onClick={async () => {
                if (!interviewToRemove) return
                try {
                  await removeInterview.mutateAsync(interviewToRemove.id)
                  setInterviewToRemove(null)
                  toast.success("Interview removed; original evidence kept")
                } catch {
                  toast.error("Could not remove the interview. Try again.")
                }
              }}
            >
              {removeInterview.isPending ? "Removing…" : "Remove interview"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <Dialog
        open={Boolean(removeLink)}
        onOpenChange={(value) => {
          if (!value && !unlinking) setRemoveLink(null)
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {unlinkingEvidence ? "Unlink evidence?" : "Unlink this item?"}
            </DialogTitle>
            <DialogDescription>
              {unlinkingEvidence
                ? `Remove ${removeLink?.label || "this file"} from this dossier. The original evidence file and other dossier links stay unchanged.`
                : `Remove ${removeLink?.label || "this item"} from this dossier. The item itself and other dossier links stay unchanged.`}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="ghost"
              disabled={unlinking}
              onClick={() => setRemoveLink(null)}
            >
              Cancel
            </Button>
            <Button
              disabled={unlinking}
              onClick={async () => {
                if (!removeLink) return
                try {
                  if (unlinkingEvidence)
                    await removeEvidence.mutateAsync(removeLink.target_id)
                  else await removeOtherLink.mutateAsync(removeLink.id)
                  setRemoveLink(null)
                  toast.success(
                    unlinkingEvidence
                      ? "Evidence unlinked"
                      : "Unlinked from this dossier"
                  )
                } catch {
                  toast.error(
                    unlinkingEvidence
                      ? "Could not unlink evidence. Try again."
                      : "Could not unlink this item. Try again."
                  )
                }
              }}
            >
              {unlinking
                ? "Unlinking…"
                : unlinkingEvidence
                  ? "Unlink evidence"
                  : "Unlink"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Sheet>
  )
}

/** Long working notes stay collapsed to three lines so the interview list stays readable (FEAT-010 compact view). */
function InterviewNotes({ text }: { text: string }) {
  const [open, setOpen] = useState(false)
  const long = text.length > 280 || text.split("\n").length > 3
  return (
    <div className="mt-2">
      <p
        className={`whitespace-pre-wrap text-xs leading-relaxed ${open || !long ? "" : "line-clamp-3"}`}
      >
        {text}
      </p>
      {long ? (
        <button
          type="button"
          className="mt-1 text-[11px] text-muted-foreground underline"
          onClick={() => setOpen(!open)}
        >
          {open ? "Show less" : "Show full notes"}
        </button>
      ) : null}
    </div>
  )
}
