import { useEffect, useState } from "react"
import { FileImage, Plus } from "lucide-react"
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
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { dossiersAPI } from "../api"
import { useQueryClient } from "@tanstack/react-query"
import { DossierPicker } from "./DossierPicker"

const IMAGE = /\.(avif|bmp|gif|heic|jpe?g|png|tiff?|webp)$/i

export function AddEvidenceToDossierDialog({
  caseId,
  files,
  open,
  onOpenChange,
  onDone,
}: {
  caseId: string
  files: Array<{ id: string; name: string }>
  open: boolean
  onOpenChange: (value: boolean) => void
  onDone?: () => void
}) {
  const [selected, setSelected] = useState<string | null>(null)
  const [newName, setNewName] = useState("")
  const [saving, setSaving] = useState(false)
  const client = useQueryClient()
  const [selectedName, setSelectedName] = useState("")
  useEffect(() => {
    if (!open) {
      setSelected(null)
      setSelectedName("")
      setNewName("")
    }
  }, [open])
  const attach = async () => {
    setSaving(true)
    try {
      let dossierId = selected
      if (!dossierId) {
        if (!newName.trim()) return
        dossierId = (
          await dossiersAPI.create({
            case_id: caseId,
            display_name: newName.trim(),
            dossier_type: "other",
          })
        ).id
      }
      setSelected(dossierId)
      // Add without replacing another investigator's links. Repeating this call is safe.
      await dossiersAPI.addEvidence(dossierId, [
        ...new Set(files.map((file) => file.id)),
      ])
      const images = files.filter((file) => IMAGE.test(file.name))
      if (images.length) {
        const dossier = await dossiersAPI.get(dossierId)
        const existingImages = new Set(
          (dossier.media ?? []).map((item) => item.evidence_file_id)
        )
        let hasCover = Boolean(dossier.media?.some((item) => item.is_cover))
        for (const image of images) {
          if (existingImages.has(image.id)) continue
          await dossiersAPI.addMedia(dossierId, {
            evidence_file_id: image.id,
            is_cover: !hasCover,
          })
          hasCover = true
          existingImages.add(image.id)
        }
      }
      toast.success(
        `${files.length} evidence item${files.length === 1 ? "" : "s"} added to Dossier`
      )
      onDone?.()
      onOpenChange(false)
    } catch (error) {
      toast.error(
        error instanceof Error
          ? `${error.message}. Any completed links are kept; you can retry safely.`
          : "Could not finish adding evidence. You can retry safely."
      )
    } finally {
      await client.invalidateQueries({ queryKey: ["dossiers"] })
      setSaving(false)
    }
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add evidence to Dossier</DialogTitle>
          <DialogDescription>
            Add the selected evidence to an existing Dossier or start a new
            unlinked one.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="rounded-lg border border-border bg-muted/20 p-3">
            <p className="text-xs font-medium">
              {files.length} selected item{files.length === 1 ? "" : "s"}
            </p>
            <p className="mt-1 text-[11px] text-muted-foreground">
              All files link to the dossier; images also join its gallery.
              Original evidence stays unchanged.
            </p>
          </div>
          <div className="space-y-2">
            <Label>Existing Dossier</Label>
            {selected && (
              <p className="text-xs font-medium" role="status">
                Selected: {selectedName || newName}
              </p>
            )}
            <DossierPicker
              caseId={caseId}
              selectedDossierIds={selected ? [selected] : []}
              onSelect={(dossier) => {
                setSelected(dossier.id)
                setSelectedName(dossier.display_name)
                setNewName("")
              }}
            />
          </div>
          <div className="relative py-1 text-center text-[10px] uppercase tracking-wider text-muted-foreground before:absolute before:left-0 before:right-0 before:top-1/2 before:border-t before:border-border">
            <span className="relative bg-background px-2">or create new</span>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="new-dossier-from-evidence">
              New unlinked Dossier name
            </Label>
            <div className="relative">
              <FileImage className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                id="new-dossier-from-evidence"
                value={newName}
                onChange={(event) => {
                  setNewName(event.target.value)
                  setSelected(null)
                }}
                className="pl-9"
                placeholder="Working subject name…"
              />
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="primary"
            disabled={(!selected && !newName.trim()) || saving}
            onClick={() => void attach()}
          >
            <Plus className="size-4" /> {saving ? "Adding…" : "Add to Dossier"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
