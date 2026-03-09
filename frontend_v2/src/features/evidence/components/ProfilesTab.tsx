import { useState } from "react"
import { useParams } from "react-router-dom"
import { Plus, Settings, FolderOpen } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { EmptyState } from "@/components/ui/empty-state"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { ProfileCard } from "./ProfileCard"
import { ProfileEditorDialog } from "./ProfileEditorDialog"
import { FolderProfileWizard } from "./FolderProfileWizard"
import { useProfiles, useDeleteProfile } from "../hooks/use-profiles"
import { toast } from "sonner"

export function ProfilesTab() {
  const { id: caseId } = useParams()
  const { data: profiles, isLoading } = useProfiles()
  const deleteMutation = useDeleteProfile()
  const [editorOpen, setEditorOpen] = useState(false)
  const [editingProfile, setEditingProfile] = useState<string | undefined>()
  const [cloneFrom, setCloneFrom] = useState<string | undefined>()
  const [wizardOpen, setWizardOpen] = useState(false)
  const [wizardFolderPath, setWizardFolderPath] = useState("")

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
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setWizardOpen(true)}
          >
            <FolderOpen className="size-3.5" />
            Folder Wizard
          </Button>
          <Button variant="primary" size="sm" onClick={handleNew}>
            <Plus className="size-3.5" />
            New Profile
          </Button>
        </div>
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

      {/* Folder Profile Wizard — prompt for folder path then open wizard */}
      {wizardOpen && !wizardFolderPath && (
        <div className="mt-6 rounded-lg border border-border bg-card p-4">
          <p className="mb-2 text-sm font-medium">Enter folder path for wizard</p>
          <form
            className="flex items-center gap-2"
            onSubmit={(e) => {
              e.preventDefault()
              const fd = new FormData(e.currentTarget)
              const path = (fd.get("folderPath") as string)?.trim()
              if (path) setWizardFolderPath(path)
              else toast.error("Enter a folder path")
            }}
          >
            <Input
              name="folderPath"
              placeholder="e.g., evidence/wiretaps/batch-01"
              className="h-8 flex-1"
            />
            <Button variant="primary" size="sm" type="submit">
              Open Wizard
            </Button>
            <Button
              variant="outline"
              size="sm"
              type="button"
              onClick={() => setWizardOpen(false)}
            >
              Cancel
            </Button>
          </form>
        </div>
      )}

      {wizardFolderPath && caseId && (
        <FolderProfileWizard
          open={!!wizardFolderPath}
          onOpenChange={(open) => {
            if (!open) {
              setWizardFolderPath("")
              setWizardOpen(false)
            }
          }}
          caseId={caseId}
          folderPath={wizardFolderPath}
          onComplete={(config) => {
            toast.success("Folder profile configuration saved")
            console.log("Folder profile config:", config)
          }}
        />
      )}
    </div>
  )
}
