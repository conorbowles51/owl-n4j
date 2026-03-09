import { useState } from "react"
import { Plus, Settings } from "lucide-react"
import { Button } from "@/components/ui/button"
import { EmptyState } from "@/components/ui/empty-state"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { ProfileCard } from "./ProfileCard"
import { ProfileEditorDialog } from "./ProfileEditorDialog"
import { useProfiles, useDeleteProfile } from "../hooks/use-profiles"
import { toast } from "sonner"

export function ProfilesTab() {
  const { data: profiles, isLoading } = useProfiles()
  const deleteMutation = useDeleteProfile()
  const [editorOpen, setEditorOpen] = useState(false)
  const [editingProfile, setEditingProfile] = useState<string | undefined>()
  const [cloneFrom, setCloneFrom] = useState<string | undefined>()

  const handleEdit = (name: string) => {
    setEditingProfile(name)
    setCloneFrom(undefined)
    setEditorOpen(true)
  }

  const handleClone = (name: string) => {
    setEditingProfile(undefined)
    setCloneFrom(name)
    setEditorOpen(true)
  }

  const handleDelete = (name: string) => {
    if (!confirm(`Delete profile "${name}"?`)) return
    deleteMutation.mutate(name, {
      onSuccess: () => toast.success("Profile deleted"),
      onError: () => toast.error("Failed to delete profile"),
    })
  }

  const handleNew = () => {
    setEditingProfile(undefined)
    setCloneFrom(undefined)
    setEditorOpen(true)
  }

  return (
    <div className="p-6">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-foreground">Processing Profiles</h2>
        <Button variant="primary" size="sm" onClick={handleNew}>
          <Plus className="size-3.5" />
          New Profile
        </Button>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-12">
          <LoadingSpinner />
        </div>
      ) : !profiles?.length ? (
        <EmptyState
          icon={Settings}
          title="No profiles"
          description="Create a processing profile to customize how evidence is analyzed"
          className="py-12"
        />
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {profiles.map((profile) => (
            <ProfileCard
              key={profile.name}
              profile={profile}
              onEdit={handleEdit}
              onDelete={handleDelete}
              onClone={handleClone}
            />
          ))}
        </div>
      )}

      <ProfileEditorDialog
        open={editorOpen}
        onOpenChange={setEditorOpen}
        editingProfile={editingProfile}
        cloneFrom={cloneFrom}
      />
    </div>
  )
}
