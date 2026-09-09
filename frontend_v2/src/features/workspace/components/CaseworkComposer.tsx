import { useEffect, useMemo, useRef, useState } from "react"
import {
  Bold,
  CheckCircle2,
  CircleHelp,
  Heading2,
  Info,
  Italic,
  Link2,
  List,
  Loader2,
  MessageSquareText,
  MinusCircle,
  Paperclip,
  Plus,
  Quote,
  Save,
  Tag,
  X,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import { cn } from "@/lib/cn"
import type {
  CaseworkEntry,
  CaseworkEntryType,
  CaseworkLinkInput,
  FindingSignificance,
  LinkRelationship,
} from "../casework-api"
import {
  ENTRY_LABELS,
  linkKey,
  linkLabel,
  RELATIONSHIP_LABELS,
  toLinkInput,
} from "../casework-utils"
import { CaseworkAttachmentPicker } from "./CaseworkAttachmentPicker"

export interface CaseworkComposerValue {
  entry_type: CaseworkEntryType
  title: string | null
  body: string
  tags: string[]
  significance: FindingSignificance | null
  confidence: number | null
  confidence_rationale: string | null
  links: CaseworkLinkInput[]
}

interface CaseworkComposerProps {
  caseId: string
  initialEntry?: CaseworkEntry | null
  initialType?: CaseworkEntryType
  initialLinks?: CaseworkLinkInput[]
  currentSelection?: CaseworkLinkInput[]
  canEdit?: boolean
  compact?: boolean
  saving?: boolean
  submitLabel?: string
  onSubmit: (value: CaseworkComposerValue) => Promise<void> | void
  onCancel?: () => void
}

const RELATIONSHIPS: Array<{
  value: LinkRelationship
  icon: typeof CircleHelp
  description: string
}> = [
  { value: "unclassified", icon: CircleHelp, description: "No assessment yet" },
  { value: "supports", icon: CheckCircle2, description: "Supports this entry" },
  { value: "contradicts", icon: MinusCircle, description: "Contradicts this entry" },
  { value: "context", icon: Info, description: "Background or context" },
]

const FORMAT_ACTIONS = [
  { label: "Bold", icon: Bold, before: "**", after: "**", placeholder: "text" },
  { label: "Italic", icon: Italic, before: "_", after: "_", placeholder: "text" },
  { label: "Heading", icon: Heading2, before: "## ", after: "", placeholder: "Heading" },
  { label: "Bulleted list", icon: List, before: "- ", after: "", placeholder: "List item" },
  { label: "Quote", icon: Quote, before: "> ", after: "", placeholder: "Quote" },
  { label: "Link", icon: Link2, before: "[", after: "](https://)", placeholder: "label" },
]

const EMPTY_LINKS: CaseworkLinkInput[] = []

function mergeLinks(existing: CaseworkLinkInput[], incoming: CaseworkLinkInput[]) {
  const next = existing.map(toLinkInput)
  const seen = new Set(next.map(linkKey))
  for (const link of incoming) {
    if (!seen.has(linkKey(link))) {
      next.push(toLinkInput(link))
      seen.add(linkKey(link))
    }
  }
  return next
}

function initialValue(
  entry: CaseworkEntry | null | undefined,
  type: CaseworkEntryType,
  links: CaseworkLinkInput[],
): CaseworkComposerValue {
  return {
    entry_type: entry?.entry_type ?? type,
    title: entry?.title ?? null,
    body: entry?.body ?? "",
    tags: entry?.tags ?? [],
    significance:
      entry?.entry_type === "finding" ? entry.significance ?? "medium" : "medium",
    confidence: entry?.entry_type === "theory" ? entry.confidence ?? null : null,
    confidence_rationale: null,
    links: entry?.links.map(toLinkInput) ?? links.map(toLinkInput),
  }
}

export function CaseworkComposer({
  caseId,
  initialEntry,
  initialType = "note",
  initialLinks = EMPTY_LINKS,
  currentSelection = EMPTY_LINKS,
  canEdit = true,
  compact = false,
  saving = false,
  submitLabel,
  onSubmit,
  onCancel,
}: CaseworkComposerProps) {
  const [value, setValue] = useState(() =>
    initialValue(initialEntry, initialType, initialLinks),
  )
  const [tagDraft, setTagDraft] = useState("")
  const [pickerOpen, setPickerOpen] = useState(false)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const bodyRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    setValue(initialValue(initialEntry, initialType, initialLinks))
    setErrors({})
  }, [initialEntry, initialLinks, initialType])

  const needsConfidenceRationale =
    initialEntry?.entry_type === "theory" &&
    initialEntry.confidence !== null &&
    initialEntry.confidence !== undefined &&
    value.confidence !== initialEntry.confidence

  const validation = useMemo(() => {
    const next: Record<string, string> = {}
    if (!value.body.trim()) next.body = "Add some casework before saving."
    if (value.entry_type !== "note" && !value.title?.trim()) {
      next.title = `${ENTRY_LABELS[value.entry_type]} title is required.`
    }
    if (needsConfidenceRationale && !value.confidence_rationale?.trim()) {
      next.confidence_rationale = "Explain why the confidence assessment changed."
    }
    return next
  }, [needsConfidenceRationale, value])

  const insertMarkdown = (before: string, after = before, placeholder = "text") => {
    const textarea = bodyRef.current
    if (!textarea) return
    const start = textarea.selectionStart
    const end = textarea.selectionEnd
    const selected = value.body.slice(start, end) || placeholder
    const body = `${value.body.slice(0, start)}${before}${selected}${after}${value.body.slice(end)}`
    setValue((current) => ({ ...current, body }))
    requestAnimationFrame(() => {
      textarea.focus()
      textarea.setSelectionRange(start + before.length, start + before.length + selected.length)
    })
  }

  const addTag = () => {
    const tag = tagDraft.trim().replace(/^#/, "")
    if (!tag || value.tags.includes(tag) || value.tags.length >= 20) return
    setValue((current) => ({ ...current, tags: [...current.tags, tag] }))
    setTagDraft("")
  }

  const submit = async () => {
    if (!canEdit || saving) return
    if (Object.keys(validation).length) {
      setErrors(validation)
      return
    }
    setErrors({})
    await onSubmit({
      ...value,
      title: value.title?.trim() || null,
      body: value.body.trim(),
      tags: value.tags.map((tag) => tag.trim()).filter(Boolean),
      significance: value.entry_type === "finding" ? value.significance : null,
      confidence: value.entry_type === "theory" ? value.confidence : null,
      confidence_rationale:
        value.entry_type === "theory"
          ? value.confidence_rationale?.trim() || null
          : null,
      links: value.links.map(toLinkInput),
    })
  }

  return (
    <div className={cn("space-y-4", compact && "space-y-3")}>
      {!initialEntry && (
        <fieldset disabled={!canEdit}>
          <legend className="sr-only">Casework type</legend>
          <div className="grid grid-cols-3 gap-1 rounded-lg border border-border bg-muted/35 p-1">
            {(["note", "finding", "theory"] as CaseworkEntryType[]).map((type) => (
              <button
                key={type}
                type="button"
                aria-pressed={value.entry_type === type}
                onClick={() =>
                  setValue((current) => ({
                    ...current,
                    entry_type: type,
                    title: type === "note" ? current.title : current.title ?? "",
                  }))
                }
                className={cn(
                  "rounded-md px-2 py-1.5 text-xs font-medium transition-colors",
                  value.entry_type === type
                    ? "bg-background text-foreground shadow-sm ring-1 ring-border"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {ENTRY_LABELS[type]}
              </button>
            ))}
          </div>
        </fieldset>
      )}

      <div className="space-y-1.5">
        <Label htmlFor="casework-title">
          Title {value.entry_type === "note" && <span className="font-normal text-muted-foreground">(optional)</span>}
        </Label>
        <Input
          id="casework-title"
          value={value.title ?? ""}
          disabled={!canEdit}
          aria-invalid={!!errors.title}
          onChange={(event) => setValue((current) => ({ ...current, title: event.target.value }))}
          placeholder={`${ENTRY_LABELS[value.entry_type]} title`}
          className="bg-background font-medium"
        />
        {errors.title && <p className="text-xs text-destructive" role="alert">{errors.title}</p>}
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="casework-body">Casework</Label>
        <div className="overflow-hidden rounded-lg border border-input bg-background focus-within:border-ring focus-within:ring-[3px] focus-within:ring-ring/20">
          <div className="flex items-center gap-0.5 border-b border-border bg-muted/25 p-1" aria-label="Formatting toolbar">
            {FORMAT_ACTIONS.map(({ label, icon: Icon, before, after, placeholder }) => (
              <Button
                key={label}
                type="button"
                variant="ghost"
                size="icon-sm"
                className="size-7"
                title={label}
                aria-label={label}
                disabled={!canEdit}
                onClick={() => insertMarkdown(before, after, placeholder)}
              >
                <Icon className="size-3.5" />
              </Button>
            ))}
            <span className="ml-auto px-1.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">Markdown</span>
          </div>
          <Textarea
            ref={bodyRef}
            id="casework-body"
            value={value.body}
            disabled={!canEdit}
            aria-invalid={!!errors.body}
            onChange={(event) => setValue((current) => ({ ...current, body: event.target.value }))}
            placeholder="Record the observation, reasoning, or working theory…"
            className={cn(
              "min-h-40 resize-y rounded-none border-0 bg-transparent leading-relaxed shadow-none focus-visible:ring-0",
              compact && "min-h-28",
            )}
          />
        </div>
        {errors.body && <p className="text-xs text-destructive" role="alert">{errors.body}</p>}
      </div>

      {value.entry_type === "finding" && (
        <div className="space-y-1.5">
          <Label htmlFor="casework-significance">Significance</Label>
          <Select
            value={value.significance ?? "medium"}
            disabled={!canEdit}
            onValueChange={(next: FindingSignificance) =>
              setValue((current) => ({ ...current, significance: next }))
            }
          >
            <SelectTrigger id="casework-significance" className="w-full"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="high">High — materially affects the case</SelectItem>
              <SelectItem value="medium">Medium — relevant and actionable</SelectItem>
              <SelectItem value="low">Low — useful context</SelectItem>
            </SelectContent>
          </Select>
        </div>
      )}

      {value.entry_type === "theory" && (
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="casework-confidence">Confidence</Label>
            <Select
              value={value.confidence === null ? "unassessed" : String(value.confidence)}
              disabled={!canEdit}
              onValueChange={(next) =>
                setValue((current) => ({
                  ...current,
                  confidence: next === "unassessed" ? null : Number(next),
                }))
              }
            >
              <SelectTrigger id="casework-confidence" className="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="unassessed">Not assessed</SelectItem>
                {Array.from({ length: 21 }, (_, index) => index * 5).map((score) => (
                  <SelectItem key={score} value={String(score)}>{score}%</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {(needsConfidenceRationale || value.confidence_rationale) && (
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="casework-confidence-rationale">Why did confidence change?</Label>
              <Textarea
                id="casework-confidence-rationale"
                value={value.confidence_rationale ?? ""}
                disabled={!canEdit}
                aria-invalid={!!errors.confidence_rationale}
                onChange={(event) =>
                  setValue((current) => ({ ...current, confidence_rationale: event.target.value }))
                }
                className="min-h-20 bg-background"
                placeholder="Briefly identify the new evidence or reasoning."
              />
              {errors.confidence_rationale && (
                <p className="text-xs text-destructive" role="alert">{errors.confidence_rationale}</p>
              )}
            </div>
          )}
        </div>
      )}

      <div className="space-y-2">
        <Label htmlFor="casework-tags" className="flex items-center gap-1.5"><Tag className="size-3.5" /> Tags</Label>
        <div className="flex gap-2">
          <Input
            id="casework-tags"
            value={tagDraft}
            disabled={!canEdit || value.tags.length >= 20}
            onChange={(event) => setTagDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === ",") {
                event.preventDefault()
                addTag()
              }
            }}
            placeholder="Type a tag and press Enter"
            className="h-8 bg-background text-xs"
          />
          <Button type="button" variant="outline" size="sm" disabled={!tagDraft.trim() || !canEdit} onClick={addTag}>
            <Plus className="size-3.5" /> Add
          </Button>
        </div>
        {!!value.tags.length && (
          <div className="flex flex-wrap gap-1.5">
            {value.tags.map((tag) => (
              <span key={tag} className="inline-flex items-center gap-1 rounded-full border border-border bg-muted/40 px-2 py-0.5 text-[11px] font-medium">
                {tag}
                {canEdit && (
                  <button type="button" aria-label={`Remove ${tag} tag`} onClick={() => setValue((current) => ({ ...current, tags: current.tags.filter((item) => item !== tag) }))}>
                    <X className="size-3 text-muted-foreground" />
                  </button>
                )}
              </span>
            ))}
          </div>
        )}
      </div>

      <section className="space-y-2" aria-labelledby="casework-links-heading">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <Label id="casework-links-heading" className="flex items-center gap-1.5"><Paperclip className="size-3.5" /> Linked items</Label>
          <div className="flex items-center gap-1.5">
            {!!currentSelection.length && canEdit && (
              <Button type="button" variant="ghost" size="sm" className="h-7 text-[11px]" onClick={() => setValue((current) => ({ ...current, links: mergeLinks(current.links, currentSelection) }))}>
                Attach selection ({currentSelection.length})
              </Button>
            )}
            {canEdit && (
              <Button type="button" variant="outline" size="sm" className="h-7 text-[11px]" aria-expanded={pickerOpen} onClick={() => setPickerOpen((open) => !open)}>
                <Plus className="size-3" /> Search
              </Button>
            )}
          </div>
        </div>

        {value.links.length ? (
          <div className="divide-y divide-border">
            {value.links.map((link) => {
              const relationship = link.relationship ?? "unclassified"
              const relationshipOption = RELATIONSHIPS.find((item) => item.value === relationship) ?? RELATIONSHIPS[0]
              const RelationshipIcon = relationshipOption.icon
              return (
                <div key={linkKey(link)} className="flex min-w-0 flex-wrap items-center gap-2 py-1.5">
                  <MessageSquareText className="size-3.5 shrink-0 text-muted-foreground" />
                  <span className="min-w-0 flex-1 truncate text-xs font-medium" title={link.target_label ?? undefined}>{linkLabel(link)}</span>
                  <Select
                    value={relationship}
                    disabled={!canEdit}
                    onValueChange={(next: LinkRelationship) =>
                      setValue((current) => ({
                        ...current,
                        links: current.links.map((item) =>
                          linkKey(item) === linkKey(link) ? { ...item, relationship: next } : item,
                        ),
                      }))
                    }
                  >
                    <SelectTrigger size="sm" className="h-7 w-[132px] border-0 bg-muted/45 px-2 text-[11px] shadow-none">
                      <RelationshipIcon className="size-3" aria-hidden="true" />
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent align="end">
                      {RELATIONSHIPS.map(({ value: option, icon: Icon, description }) => (
                        <SelectItem key={option} value={option}>
                          <Icon className="size-3.5" />
                          <span><span className="block">{RELATIONSHIP_LABELS[option]}</span><span className="block text-[10px] text-muted-foreground">{description}</span></span>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {canEdit && (
                    <Button type="button" variant="ghost" size="icon-sm" className="size-7 shrink-0" aria-label={`Remove ${linkLabel(link)}`} onClick={() => setValue((current) => ({ ...current, links: current.links.filter((item) => linkKey(item) !== linkKey(link)) }))}>
                      <X className="size-3.5" />
                    </Button>
                  )}
                </div>
              )
            })}
          </div>
        ) : (
          <p className="rounded-lg border border-dashed border-border px-3 py-4 text-center text-xs text-muted-foreground">
            No linked material. Search the case or attach the current selection.
          </p>
        )}

        {pickerOpen && canEdit && (
          <CaseworkAttachmentPicker
            caseId={caseId}
            onAttach={(link) => {
              setValue((current) => ({ ...current, links: mergeLinks(current.links, [link]) }))
            }}
          />
        )}
      </section>

      <div className="flex items-center justify-end gap-2 border-t border-border pt-3">
        {onCancel && <Button type="button" variant="outline" size="sm" onClick={onCancel}>Cancel</Button>}
        <Button type="button" size="sm" disabled={!canEdit || saving} onClick={submit}>
          {saving ? <Loader2 className="size-3.5 animate-spin" /> : <Save className="size-3.5" />}
          {submitLabel ?? (initialEntry ? "Save changes" : `Save ${ENTRY_LABELS[value.entry_type].toLowerCase()}`)}
        </Button>
      </div>
    </div>
  )
}
