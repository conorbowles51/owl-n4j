import { useState } from "react"
import { AlertTriangle, RefreshCw } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { ApiError } from "@/lib/api-client"
import type { CaseworkEntry, CaseworkEntryType, CaseworkLinkInput } from "../casework-api"
import {
  useChangeCaseworkConfidence,
  useChangeCaseworkSignificance,
  useCreateCaseworkEntry,
  useUpdateCaseworkEntry,
} from "../hooks/use-casework"
import { CaseworkComposer, type CaseworkComposerValue } from "./CaseworkComposer"

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
  onReload?: () => void
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
}: CaseworkEditorProps) {
  const createMutation = useCreateCaseworkEntry(caseId)
  const updateMutation = useUpdateCaseworkEntry(caseId)
  const confidenceMutation = useChangeCaseworkConfidence(caseId)
  const significanceMutation = useChangeCaseworkSignificance(caseId)
  const [conflict, setConflict] = useState(false)

  const save = async (value: CaseworkComposerValue) => {
    setConflict(false)
    try {
      let saved: CaseworkEntry
      if (!entry) {
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
          entryId: entry.id,
          input: {
            expected_version: entry.version,
            title: value.title,
            body: value.body,
            tags: value.tags,
            links: value.links,
          },
        })
        if (
          entry.entry_type === "finding" &&
          value.significance &&
          value.significance !== entry.significance
        ) {
          saved = await significanceMutation.mutateAsync({
            entryId: entry.id,
            version: saved.version,
            significance: value.significance,
          })
        }
        if (
          entry.entry_type === "theory" &&
          value.confidence !== entry.confidence
        ) {
          saved = await confidenceMutation.mutateAsync({
            entryId: entry.id,
            version: saved.version,
            confidence: value.confidence,
            rationale: value.confidence_rationale ?? undefined,
          })
        }
      }
      toast.success(`${value.entry_type[0].toUpperCase()}${value.entry_type.slice(1)} saved`)
      onSaved?.(saved)
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setConflict(true)
        return
      }
      toast.error(error instanceof Error ? error.message : "Could not save casework")
    }
  }

  const saving =
    createMutation.isPending ||
    updateMutation.isPending ||
    confidenceMutation.isPending ||
    significanceMutation.isPending

  return (
    <div className="space-y-3">
      {conflict && (
        <div className="rounded-lg border border-amber-300/70 bg-amber-50 p-3 text-amber-950 dark:border-amber-800 dark:bg-amber-950/35 dark:text-amber-100" role="alert">
          <div className="flex items-start gap-2">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" />
            <div className="min-w-0 flex-1">
              <p className="text-xs font-semibold">This entry changed while you were editing.</p>
              <p className="mt-1 text-xs leading-relaxed opacity-80">Reload the current version before making your changes again. Your draft remains visible until you reload.</p>
            </div>
            {onReload && (
              <Button type="button" variant="outline" size="sm" className="h-7 bg-background/70 text-[11px]" onClick={onReload}>
                <RefreshCw className="size-3" /> Reload
              </Button>
            )}
          </div>
        </div>
      )}
      <CaseworkComposer
        caseId={caseId}
        initialEntry={entry}
        initialType={initialType}
        initialLinks={initialLinks}
        currentSelection={currentSelection}
        canEdit={canEdit}
        compact={compact}
        saving={saving}
        onSubmit={save}
        onCancel={onCancel}
      />
    </div>
  )
}
