import { useState } from "react"
import { CalendarPlus, ContactRound, Link2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { AddToTimelineDialog } from "@/features/timeline/components/AddToTimelineDialog"
import { AddToEventDialog } from "@/features/timeline/components/AddToEventDialog"
import { AddEvidenceToDossierDialog } from "@/features/dossiers/components/AddEvidenceToDossierDialog"

/** "Add to Timeline", "Add to event" and "Add to Dossier" for one or several evidence files (photos first). */
export function FileAddActions({
  caseId,
  files,
  size = "sm",
  onDone,
}: {
  caseId: string
  files: Array<{ id: string; name: string }>
  size?: "sm" | "xs"
  onDone?: () => void
}) {
  const [open, setOpen] = useState<"timeline" | "event" | "dossier" | null>(null)
  const close = () => setOpen(null)
  const buttonSize = size === "xs" ? "sm" : size
  return (
    <>
      <Button size={buttonSize} variant="outline" onClick={() => setOpen("timeline")}>
        <CalendarPlus className="mr-1.5 size-3.5" /> Add to Timeline
      </Button>
      <Button size={buttonSize} variant="outline" onClick={() => setOpen("event")}>
        <Link2 className="mr-1.5 size-3.5" /> Add to event
      </Button>
      <Button size={buttonSize} variant="outline" onClick={() => setOpen("dossier")}>
        <ContactRound className="mr-1.5 size-3.5" /> Add to Dossier
      </Button>
      {open === "timeline" && (
        <AddToTimelineDialog
          caseId={caseId}
          ids={files.map((file) => file.id)}
          sourceKind="evidence_file"
          title={`${files.length} selected file${files.length === 1 ? "" : "s"}`}
          onClose={() => {
            close()
            onDone?.()
          }}
        />
      )}
      {open === "event" && <AddToEventDialog caseId={caseId} files={files} onClose={close} onDone={onDone} />}
      <AddEvidenceToDossierDialog
        caseId={caseId}
        files={open === "dossier" ? files : []}
        open={open === "dossier"}
        onOpenChange={(value) => {
          if (!value) close()
        }}
        onDone={onDone}
      />
    </>
  )
}
