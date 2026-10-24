import { useState } from "react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { dossiersAPI, type Dossier } from "../api"
import { useDossierMutation } from "../hooks"
import { DossierEvidencePicker } from "./DossierEvidencePicker"

export function AddDossierEvidenceDialog({
  dossier,
  onClose,
}: {
  dossier: Dossier
  onClose: () => void
}) {
  const [selected, setSelected] = useState<
    Array<{ id: string; label: string }>
  >([])
  const add = useDossierMutation(dossier.case_id, dossier.id, (ids: string[]) =>
    dossiersAPI.addEvidence(dossier.id, ids)
  )
  const existing = (dossier.links ?? [])
    .filter((link) => link.target_type === "evidence")
    .map((link) => link.target_id)
  const save = async () => {
    try {
      await add.mutateAsync(selected.map((item) => item.id))
      toast.success("Evidence linked to dossier")
      onClose()
    } catch (error) {
      toast.error(
        error instanceof Error
          ? error.message
          : "Could not link evidence. Your selection is kept; try again."
      )
    }
  }
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !add.isPending) onClose()
      }}
    >
      <DialogContent className="max-h-[calc(100dvh-2rem)] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Add evidence to {dossier.display_name}</DialogTitle>
          <DialogDescription>
            Link source files to this dossier. The original files stay in
            Evidence.
          </DialogDescription>
        </DialogHeader>
        {selected.length > 0 && (
          <ul className="space-y-1 rounded-lg border p-3">
            {selected.map((item) => (
              <li
                key={item.id}
                className="flex min-w-0 items-center gap-2 text-xs"
              >
                <span className="min-w-0 flex-1 break-all">{item.label}</span>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={add.isPending}
                  onClick={() =>
                    setSelected((items) =>
                      items.filter((value) => value.id !== item.id)
                    )
                  }
                  aria-label={`Remove ${item.label} from selection`}
                >
                  Remove
                </Button>
              </li>
            ))}
          </ul>
        )}
        <DossierEvidencePicker
          caseId={dossier.case_id}
          selectedIds={[...existing, ...selected.map((item) => item.id)]}
          onSelect={(item) => setSelected((items) => [...items, item])}
        />
        <DialogFooter>
          <Button variant="ghost" disabled={add.isPending} onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="primary"
            disabled={!selected.length || add.isPending}
            onClick={() => void save()}
          >
            {add.isPending
              ? "Linking…"
              : `Link ${selected.length || "selected"} file${selected.length === 1 ? "" : "s"}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
