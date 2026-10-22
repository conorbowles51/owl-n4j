import { useState } from "react"
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
import { dossiersAPI, type Dossier } from "../api"
import { useDossierMutation } from "../hooks"

export function EditDossierDialog({
  dossier,
  onClose,
}: {
  dossier: Dossier
  onClose: () => void
}) {
  const [name, setName] = useState(dossier.display_name)
  const [type, setType] = useState(dossier.dossier_type)
  const [importance, setImportance] = useState(dossier.importance ?? "")
  const [roles, setRoles] = useState(
    dossier.roles.map((role) => role.name).join(", ")
  )
  const [error, setError] = useState("")
  const update = useDossierMutation<void>(dossier.case_id, dossier.id, () =>
    dossiersAPI.update(dossier.id, {
      ...(dossier.canonical_entity_key ? {} : { display_name: name.trim() }),
      dossier_type: type,
      importance: importance.trim() || null,
      roles: [
        ...new Set(
          roles
            .split(",")
            .map((role) => role.trim())
            .filter(Boolean)
        ),
      ].map((role) => ({ name: role })),
    })
  )
  const save = async (event: React.FormEvent) => {
    event.preventDefault()
    setError("")
    try {
      await update.mutateAsync()
      onClose()
    } catch {
      setError(
        "Dossier details could not be saved. Your changes are kept; try again."
      )
    }
  }
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !update.isPending) onClose()
      }}
    >
      <DialogContent className="max-h-[calc(100dvh-2rem)] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Edit dossier details</DialogTitle>
          <DialogDescription>
            Update the subject's case-specific details and roles.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={(event) => void save(event)} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="edit-dossier-name">Name</Label>
            <Input
              id="edit-dossier-name"
              required
              maxLength={255}
              disabled={
                Boolean(dossier.canonical_entity_key) || update.isPending
              }
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
            {dossier.canonical_entity_key && (
              <p className="text-xs text-muted-foreground">
                This name follows the linked graph entity.
              </p>
            )}
          </div>
          <div className="space-y-2">
            <Label htmlFor="edit-dossier-type">Subject type</Label>
            <select
              id="edit-dossier-type"
              className="h-9 w-full rounded-md border bg-background px-2 text-sm"
              value={type}
              disabled={update.isPending}
              onChange={(event) => setType(event.target.value)}
            >
              {[
                "person",
                "organisation",
                "device",
                "vehicle",
                "address",
                "event",
                "other",
              ].map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="edit-dossier-importance">
              Why this subject matters
            </Label>
            <Input
              id="edit-dossier-importance"
              value={importance}
              disabled={update.isPending}
              maxLength={255}
              onChange={(event) => setImportance(event.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="edit-dossier-roles">Roles (comma-separated)</Label>
            <Input
              id="edit-dossier-roles"
              value={roles}
              disabled={update.isPending}
              onChange={(event) => setRoles(event.target.value)}
              placeholder="Witness, Expert…"
            />
          </div>
          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}
          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              disabled={update.isPending}
              onClick={onClose}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              variant="primary"
              disabled={
                update.isPending ||
                (!dossier.canonical_entity_key && !name.trim())
              }
            >
              {update.isPending ? "Saving…" : "Save dossier details"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
