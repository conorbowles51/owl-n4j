import { useState } from "react"
import { Plus, X } from "lucide-react"
import { useQueries } from "@tanstack/react-query"
import { toast } from "sonner"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { CaseProfilePicker, CaseProfileTypeBadge } from "@/features/case-profiles/components/CaseProfilePicker"
import { caseProfilesAPI } from "@/features/case-profiles/api"
import type { CaseProfile } from "@/features/case-profiles/types"

import { evidenceTagsAPI } from "../../api"

export function FileEntityLinker({
  caseId,
  evidenceId,
  entityIds,
  onChange,
}: {
  caseId: string
  evidenceId: string
  entityIds: string[]
  onChange: (entityIds: string[]) => void
}) {
  const [picking, setPicking] = useState(false)
  const profileQueries = useQueries({
    queries: entityIds.map((id) => ({
      queryKey: ["case-profile", id],
      queryFn: () => caseProfilesAPI.get(id),
      enabled: Boolean(id),
      staleTime: 60_000,
    })),
  })
  const profilesById = new Map<string, CaseProfile>()
  profileQueries.forEach((query) => {
    if (query.data) profilesById.set(query.data.id, query.data)
  })

  async function commit(nextIds: string[]) {
    const current = new Set(entityIds)
    const next = new Set(nextIds)
    const toAdd = [...next].filter((id) => !current.has(id))
    const toRemove = [...current].filter((id) => !next.has(id))
    try {
      if (toAdd.length) await evidenceTagsAPI.linkEntities(caseId, [evidenceId], toAdd)
      if (toRemove.length) await evidenceTagsAPI.unlinkEntities(caseId, [evidenceId], toRemove)
      onChange([...next])
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to update entity links")
    }
  }

  return (
    <div className="relative">
      <div className="flex flex-wrap items-center gap-1">
        {entityIds.map((id) => {
          const profile = profilesById.get(id)
          return (
            <Badge key={id} variant="outline" className="max-w-full gap-1 rounded-full text-[11px]">
              <span className="max-w-40 truncate">{profile?.display_name ?? id}</span>
              {profile ? <CaseProfileTypeBadge type={profile.profile_type} /> : null}
              <button type="button" onClick={() => void commit(entityIds.filter((item) => item !== id))} title="Remove link">
                <X className="size-2.5" />
              </button>
            </Badge>
          )
        })}
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-7 px-1.5 text-[11px]"
          onClick={() => setPicking((current) => !current)}
        >
          <Plus className="size-3" />
          entity
        </Button>
      </div>
      {picking ? (
        <div className="absolute left-0 top-8 z-40 w-80">
          <CaseProfilePicker
            caseId={caseId}
            selectedProfileIds={entityIds}
            placeholder="Search case profiles..."
            onSelect={(profile) => {
              void commit(entityIds.includes(profile.id) ? entityIds : [...entityIds, profile.id])
            }}
          />
        </div>
      ) : null}
    </div>
  )
}
