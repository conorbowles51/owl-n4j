import { useEffect, useState } from "react"
import { ContactRound, FileImage, Plus } from "lucide-react"
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
import { useDossiers } from "../hooks"

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
  const dossiers = useDossiers({ caseId, limit: 100 })
  useEffect(() => {
    if (!open) {
      setSelected(null)
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
      const dossier = await dossiersAPI.get(dossierId)
      const links = [
        ...(dossier.links ?? []).map((link) => ({
          target_type: link.target_type,
          target_id: link.target_id,
          relationship_type: link.relationship_type,
          label: link.label,
          source_anchor: link.source_anchor,
        })),
      ]
      for (const file of files) {
        if (IMAGE.test(file.name)) {
          await dossiersAPI.addMedia(dossierId, {
            evidence_file_id: file.id,
            is_cover: !dossier.media?.length,
          })
        } else if (
          !links.some(
            (link) =>
              link.target_type === "evidence" && link.target_id === file.id
          )
        ) {
          links.push({
            target_type: "evidence",
            target_id: file.id,
            relationship_type: "context",
            label: file.name,
            source_anchor: {},
          })
        }
      }
      if (links.length !== (dossier.links?.length ?? 0))
        await dossiersAPI.replaceLinks(dossierId, links)
      toast.success(
        `${files.length} evidence item${files.length === 1 ? "" : "s"} added to Dossier`
      )
      onDone?.()
      onOpenChange(false)
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Could not update Dossier"
      )
    } finally {
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
              Images join the gallery; other files become contextual evidence
              links. Sources remain unchanged.
            </p>
          </div>
          <div className="space-y-2">
            <Label>Existing Dossier</Label>
            <div className="max-h-52 space-y-1 overflow-y-auto rounded-lg border border-border p-1.5">
              {dossiers.data?.dossiers.map((dossier) => (
                <button
                  key={dossier.id}
                  type="button"
                  onClick={() => {
                    setSelected(dossier.id)
                    setNewName("")
                  }}
                  className={`flex w-full items-center gap-2 rounded-md p-2 text-left text-xs hover:bg-muted ${selected === dossier.id ? "bg-brand-50 text-brand-800 dark:bg-brand-500/10 dark:text-brand-200" : ""}`}
                >
                  <ContactRound className="size-4" />
                  <span className="min-w-0 flex-1 truncate font-medium">
                    {dossier.display_name}
                  </span>
                  <span className="text-[10px] text-muted-foreground">
                    {dossier.dossier_type}
                  </span>
                </button>
              ))}
            </div>
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
