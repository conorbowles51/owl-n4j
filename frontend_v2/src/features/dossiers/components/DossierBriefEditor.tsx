import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { dossiersAPI, type Dossier } from "../api"
import { useDossierMutation } from "../hooks"

export function DossierBriefEditor({
  dossier,
  canEdit,
  onDirtyChange,
}: {
  dossier: Dossier
  canEdit: boolean
  onDirtyChange?: (dirty: boolean) => void
}) {
  const [draft, setDraft] = useState(dossier.summary ?? "")
  const [dirty, setDirty] = useState(false)
  const [error, setError] = useState("")
  const update = useDossierMutation(
    dossier.case_id,
    dossier.id,
    (summary: string) => dossiersAPI.update(dossier.id, { summary })
  )
  useEffect(() => {
    if (!dirty) setDraft(dossier.summary ?? "")
  }, [dossier.summary, dirty])
  useEffect(() => {
    onDirtyChange?.(dirty)
  }, [dirty, onDirtyChange])
  const save = async () => {
    setError("")
    try {
      await update.mutateAsync(draft)
      setDirty(false)
    } catch {
      setError(
        "Your brief could not be saved. Your writing is kept here; try again."
      )
    }
  }
  return (
    <div className="space-y-2">
      <Textarea
        aria-label="Investigator brief"
        value={draft}
        disabled={!canEdit || update.isPending}
        rows={7}
        placeholder="No investigator summary yet."
        onChange={(event) => {
          setDraft(event.target.value)
          setDirty(true)
          setError("")
        }}
      />
      {canEdit && (
        <div className="flex items-center justify-between gap-3">
          <p
            role={error ? "alert" : "status"}
            className={
              error
                ? "text-xs text-destructive"
                : "text-xs text-muted-foreground"
            }
          >
            {error ||
              (update.isPending
                ? "Saving…"
                : dirty
                  ? "Unsaved changes"
                  : "Saved")}
          </p>
          <Button
            size="sm"
            disabled={!dirty || update.isPending}
            onClick={() => void save()}
          >
            {update.isPending ? "Saving…" : error ? "Retry save" : "Save brief"}
          </Button>
        </div>
      )}
    </div>
  )
}
