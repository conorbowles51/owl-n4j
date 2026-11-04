import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { dossiersAPI, type RemovedRecord } from "../api"
import { dossierKeys } from "../hooks"

const KIND: Record<RemovedRecord["kind"], string> = {
  dossier_assessment: "Assessment",
  dossier_interview: "Interview",
  dossier_media: "Media",
  dossier_link: "Link",
  dossier_evidence_link: "Evidence link",
}

function when(value?: string | null) {
  return value
    ? new Intl.DateTimeFormat(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(new Date(value))
    : ""
}

/**
 * Assessments, interviews, media and links removed from this dossier, each kept as it was, with Put back
 * (followups m11032229063349: a removal used to leave nothing to restore).
 */
export function RemovedFromDossier({
  caseId,
  dossierId,
  canEdit,
}: {
  caseId: string
  dossierId: string
  canEdit: boolean
}) {
  const client = useQueryClient()
  const removed = useQuery({
    queryKey: dossierKeys.removed(dossierId),
    queryFn: () => dossiersAPI.removed(caseId, dossierId),
  })
  const putBack = useMutation({
    mutationFn: (id: string) => dossiersAPI.putBack(caseId, id),
    onSuccess: () => {
      toast.success("Put back as it was")
      return Promise.all([
        client.invalidateQueries({ queryKey: dossierKeys.removed(dossierId) }),
        client.invalidateQueries({ queryKey: ["dossiers", "detail", dossierId] }),
        client.invalidateQueries({ queryKey: ["dossiers", "list", caseId] }),
      ])
    },
    onError: (error: Error) =>
      toast.error(error.message || "Could not put it back. Try again."),
  })
  const items = removed.data?.items ?? []
  if (!items.length) return null
  return (
    <details className="mx-5 mb-5 rounded border p-3 text-sm">
      <summary className="cursor-pointer font-medium">
        Removed from this dossier ({items.length})
      </summary>
      <ul className="mt-2 space-y-2" aria-label="Removed from this dossier">
        {items.map((item) => (
          <li key={item.id} className="flex flex-wrap items-center gap-2">
            <span className="min-w-0 flex-1">
              <span className="font-medium">{KIND[item.kind]}</span>
              {item.label ? `: ${item.label}` : ""}
              <span className="block text-xs text-muted-foreground">
                Removed {when(item.removed_at)}
                {item.removed_by ? ` by ${item.removed_by}` : ""}
              </span>
            </span>
            {canEdit && (
              <Button
                size="sm"
                variant="outline"
                disabled={putBack.isPending}
                onClick={() => putBack.mutate(item.id)}
              >
                Put back
              </Button>
            )}
          </li>
        ))}
      </ul>
      {removed.data?.clipped && (
        <p className="mt-2 text-xs">{removed.data.clipped}</p>
      )}
    </details>
  )
}
