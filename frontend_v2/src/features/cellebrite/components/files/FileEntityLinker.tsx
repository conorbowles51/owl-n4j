import { useState } from "react"
import { Plus, X } from "lucide-react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { dossiersAPI } from "@/features/dossiers/api"
import { DossierPicker, DossierTypeBadge } from "@/features/dossiers/components/DossierPicker"

export function FileEntityLinker({
  caseId,
  evidenceId,
  onChange,
}: {
  caseId: string
  evidenceId: string
  onChange?: (dossierIds: string[]) => void
}) {
  const [picking, setPicking] = useState(false)
  const queryClient = useQueryClient()
  const linkedQuery = useQuery({
    queryKey: ["dossiers", "evidence", caseId, evidenceId],
    queryFn: () =>
      dossiersAPI.list({ caseId, linkedEvidenceFileId: evidenceId, limit: 200 }),
    enabled: Boolean(caseId && evidenceId),
  })
  const dossiers = linkedQuery.data?.dossiers ?? []
  const dossierIds = dossiers.map((item) => item.id)

  async function add(dossierId: string) {
    try {
      await dossiersAPI.addEvidence(dossierId, [evidenceId])
      await linkedQuery.refetch()
      await queryClient.invalidateQueries({ queryKey: ["dossiers", caseId] })
      onChange?.([...new Set([...dossierIds, dossierId])])
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to add evidence to Dossier")
    }
  }

  async function remove(dossierId: string) {
    try {
      await dossiersAPI.removeEvidence(dossierId, evidenceId)
      await linkedQuery.refetch()
      await queryClient.invalidateQueries({ queryKey: ["dossiers", caseId] })
      onChange?.(dossierIds.filter((id) => id !== dossierId))
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to remove Dossier link")
    }
  }

  return (
    <div className="relative">
      <div className="flex flex-wrap items-center gap-1">
        {dossiers.map((dossier) => (
            <Badge key={dossier.id} variant="outline" className="max-w-full gap-1 rounded-full text-[11px]">
              <span className="max-w-40 truncate">{dossier.display_name}</span>
              <DossierTypeBadge type={dossier.dossier_type} />
              <button type="button" onClick={() => void remove(dossier.id)} title="Remove Dossier link">
                <X className="size-2.5" />
              </button>
            </Badge>
        ))}
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-7 px-1.5 text-[11px]"
          onClick={() => setPicking((current) => !current)}
        >
          <Plus className="size-3" />
          Dossier
        </Button>
      </div>
      {picking ? (
        <div className="absolute left-0 top-8 z-40 w-80">
          <DossierPicker
            caseId={caseId}
            selectedDossierIds={dossierIds}
            onSelect={(dossier) => {
              if (!dossierIds.includes(dossier.id)) void add(dossier.id)
            }}
          />
        </div>
      ) : null}
    </div>
  )
}
