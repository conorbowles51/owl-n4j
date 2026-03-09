import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Edit, Trash2, Copy, Settings } from "lucide-react"
import type { ProcessingProfile } from "@/types/evidence.types"

interface ProfileCardProps {
  profile: ProcessingProfile
  onEdit: (name: string) => void
  onDelete: (name: string) => void
  onClone: (name: string) => void
}

export function ProfileCard({ profile, onEdit, onDelete, onClone }: ProfileCardProps) {
  return (
    <div className="group rounded-lg border border-border bg-card p-4 transition-colors hover:border-muted-foreground/30">
      <div className="flex items-start justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <Settings className="size-3.5 text-muted-foreground" />
            <h3 className="truncate text-sm font-medium text-foreground">
              {profile.name}
            </h3>
          </div>
          {profile.description && (
            <p className="mt-1 text-xs text-muted-foreground line-clamp-2">
              {profile.description}
            </p>
          )}
        </div>
      </div>

      <div className="mt-3 flex items-center gap-1.5">
        {profile.provider && (
          <Badge variant="slate" className="text-[10px]">
            {profile.provider}
          </Badge>
        )}
        {profile.model && (
          <Badge variant="info" className="text-[10px]">
            {profile.model}
          </Badge>
        )}
      </div>

      <div className="mt-3 flex gap-1 opacity-0 transition-opacity group-hover:opacity-100">
        <Button variant="ghost" size="sm" onClick={() => onEdit(profile.name)} className="h-7 text-xs">
          <Edit className="size-3" />
          Edit
        </Button>
        <Button variant="ghost" size="sm" onClick={() => onClone(profile.name)} className="h-7 text-xs">
          <Copy className="size-3" />
          Clone
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onDelete(profile.name)}
          className="h-7 text-xs text-red-400 hover:text-red-400"
        >
          <Trash2 className="size-3" />
          Delete
        </Button>
      </div>
    </div>
  )
}
