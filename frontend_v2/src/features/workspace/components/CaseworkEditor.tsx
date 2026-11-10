import { useEffect, useRef, useState } from "react"
import { AlertTriangle, RefreshCw } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { ApiError } from "@/lib/api-client"
import type {
  CaseworkEntry,
  CaseworkEntryType,
  CaseworkLinkInput,
} from "../casework-api"
import { caseworkAPI } from "../casework-api"
import {
  useChangeCaseworkConfidence,
  useChangeCaseworkSignificance,
  useCreateCaseworkEntry,
  useUpdateCaseworkEntry,
} from "../hooks/use-casework"
import {
  CaseworkComposer,
  type CaseworkComposerValue,
} from "./CaseworkComposer"

interface CaseworkEditorProps {
  caseId: string
  entry?: CaseworkEntry | null
  initialType?: CaseworkEntryType
  initialLinks?: CaseworkLinkInput[]
  currentSelection?: CaseworkLinkInput[]
  canEdit: boolean
  compact?: boolean
  onSaved?: (entry: CaseworkEntry) => void
  onCancel?: () => void
  onReload?: () => unknown
  onDirtyChange?: (dirty: boolean) => void
}

export function CaseworkEditor({
  caseId,
  entry,
  initialType,
  initialLinks,
  currentSelection,
  canEdit,
  compact,
  onSaved,
  onCancel,
  onReload,
  onDirtyChange,
}: CaseworkEditorProps) {
  const createMutation = useCreateCaseworkEntry(caseId)
  const updateMutation = useUpdateCaseworkEntry(caseId)
  const confidenceMutation = useChangeCaseworkConfidence(caseId)
  const significanceMutation = useChangeCaseworkSignificance(caseId)
  const [conflict, setConflict] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [draftBase, setDraftBase] = useState(entry)
  const savedEntry = useRef(entry)
  const submitting = useRef(false)
  const [saving, setSaving] = useState(false)
  const [reloading, setReloading] = useState(false)

  // A background refresh must not replace an investigator's draft. Only a new
  // entry or an explicit reload changes the edit session's starting version.
  useEffect(() => {
    if (savedEntry.current?.id !== entry?.id) {
      savedEntry.current = entry
      setDraftBase(entry)
      setConflict(false)
      setSaveError(null)
    }
  }, [entry])

  const reload = async () => {
    if (!entry) return
    setReloading(true)
    try {
      const reloaded = onReload
        ? ((await onReload()) as { data?: CaseworkEntry } | undefined)
        : undefined
      const current =
        reloaded?.data?.id === entry.id
          ? reloaded.data
          : await caseworkAPI.get(caseId, entry.id, true)
      savedEntry.current = current
      setDraftBase(current)
      setConflict(false)
      setSaveError(null)
    } catch (error) {
      setSaveError(
        error instanceof Error
          ? error.message
          : "Could not reload casework. Your draft is still here."
      )
    } finally {
      setReloading(false)
    }
  }

  const save = async (value: CaseworkComposerValue) => {
    if (!canEdit || submitting.current || conflict) return
    submitting.current = true
    setSaving(true)
    setConflict(false)
    setSaveError(null)
    let contentSaved = false
    try {
      let saved: CaseworkEntry
      const base = savedEntry.current
      if (!base) {
        saved = await createMutation.mutateAsync({
          entry_type: value.entry_type,
          title: value.title,
          body: value.body,
          tags: value.tags,
          significance: value.significance,
          confidence: value.confidence,
          confidence_rationale: value.confidence_rationale,
          links: value.links,
        })
      } else {
        saved = await updateMutation.mutateAsync({
          entryId: base.id,
          input: {
            expected_version: base.version,
            title: value.title,
            body: value.body,
            tags: value.tags,
            links: value.links,
          },
        })
        savedEntry.current = saved
        contentSaved = true
        if (
          base.entry_type === "finding" &&
          value.significance !== base.significance
        ) {
          saved = await significanceMutation.mutateAsync({
            entryId: base.id,
            version: saved.version,
            significance: value.significance,
          })
          savedEntry.current = saved
        }
        if (
          base.entry_type === "theory" &&
          value.confidence !== base.confidence
        ) {
          saved = await confidenceMutation.mutateAsync({
            entryId: base.id,
            version: saved.version,
            confidence: value.confidence,
            rationale: value.confidence_rationale ?? undefined,
          })
          savedEntry.current = saved
        }
      }
      toast.success(
        `${value.entry_type[0].toUpperCase()}${value.entry_type.slice(1)} saved`
      )
      onDirtyChange?.(false)
      onSaved?.(saved)
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setConflict(true)
        return
      }
      const message =
        error instanceof Error ? error.message : "Could not save casework"
      setSaveError(
        contentSaved
          ? `Your text and links were saved, but the assessment could not be updated. ${message} Try saving again to finish.`
          : message
      )
      toast.error(message)
    } finally {
      submitting.current = false
      setSaving(false)
    }
  }

  return (
    <div className="space-y-3">
      {conflict && (
        <div
          className="rounded-lg border border-status-warning/50 bg-status-warning-soft p-3 text-status-warning"
          role="alert"
        >
          <div className="flex items-start gap-2">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" />
            <div className="min-w-0 flex-1">
              <p className="text-xs font-semibold">
                This entry changed while you were editing.
              </p>
              <p className="mt-1 text-xs leading-relaxed opacity-80">
                Reload the current version before making your changes again.
                Your draft remains visible until you reload.
              </p>
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-10 bg-background/70 text-xs"
              disabled={reloading}
              onClick={() => void reload()}
            >
              <RefreshCw className="size-3" /> Reload
            </Button>
          </div>
        </div>
      )}
      {saveError && (
        <p
          role="alert"
          className="border-l-2 border-destructive pl-3 text-sm text-destructive"
        >
          {saveError}
        </p>
      )}
      <CaseworkComposer
        caseId={caseId}
        initialEntry={draftBase}
        initialType={initialType}
        initialLinks={initialLinks}
        currentSelection={currentSelection}
        canEdit={canEdit}
        compact={compact}
        saving={saving || reloading}
        submitDisabled={conflict}
        onSubmit={save}
        onCancel={onCancel}
        onDirtyChange={onDirtyChange}
      />
    </div>
  )
}
