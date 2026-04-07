import { useState } from "react"
import { Cpu, Plus, Trash2, Edit2, Save, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Badge } from "@/components/ui/badge"
import { InstructionListEditor } from "@/components/ui/instruction-list-editor"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { EmptyState } from "@/components/ui/empty-state"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { profilesAPI, type Profile } from "../api"

function emptyProfile(): Profile {
  return {
    name: "",
    description: "",
    context_instructions: "",
    mandatory_instructions: [],
    special_entity_types: [],
  }
}

export function ProfileManagementPage() {
  const queryClient = useQueryClient()
  const [editOpen, setEditOpen] = useState(false)
  const [editProfile, setEditProfile] = useState<Profile>(emptyProfile())
  const [newEntityName, setNewEntityName] = useState("")
  const [newEntityDesc, setNewEntityDesc] = useState("")
  const [isNew, setIsNew] = useState(false)

  const { data: profiles = [], isLoading } = useQuery({
    queryKey: ["profiles"],
    queryFn: () => profilesAPI.list(),
  })

  const saveMutation = useMutation({
    mutationFn: (profile: Profile) => profilesAPI.save(profile),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["profiles"] })
      setEditOpen(false)
      toast.success("Profile saved")
    },
    onError: (error) => toast.error(error.message || "Failed to save profile"),
  })

  const deleteMutation = useMutation({
    mutationFn: (name: string) => profilesAPI.delete(name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["profiles"] })
      toast.success("Profile deleted")
    },
    onError: (error) => toast.error(error.message || "Failed to delete profile"),
  })

  const openNew = () => {
    setEditProfile(emptyProfile())
    setNewEntityName("")
    setNewEntityDesc("")
    setIsNew(true)
    setEditOpen(true)
  }

  const openEdit = (profile: Profile) => {
    setEditProfile({
      ...profile,
      special_entity_types: [...(profile.special_entity_types ?? [])],
    })
    setNewEntityName("")
    setNewEntityDesc("")
    setIsNew(false)
    setEditOpen(true)
  }

  const addEntityType = () => {
    const name = newEntityName.trim()
    if (!name) return

    if (
      (editProfile.special_entity_types ?? []).some(
        (entity) => entity.name.toLowerCase() === name.toLowerCase()
      )
    ) {
      toast.error("Entity type already exists")
      return
    }

    setEditProfile((current) => ({
      ...current,
      special_entity_types: [
        ...(current.special_entity_types ?? []),
        {
          name,
          ...(newEntityDesc.trim() ? { description: newEntityDesc.trim() } : {}),
        },
      ],
    }))
    setNewEntityName("")
    setNewEntityDesc("")
  }

  const removeEntityType = (index: number) => {
    setEditProfile((current) => ({
      ...current,
      special_entity_types: (current.special_entity_types ?? []).filter(
        (_, itemIndex) => itemIndex !== index
      ),
    }))
  }

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 border-b border-border px-4 py-2">
        <Cpu className="size-4 text-amber-500" />
        <span className="text-sm font-semibold">Profile Management</span>
        <div className="flex-1" />
        <Badge variant="slate">{profiles.length} profiles</Badge>
        <Button variant="primary" size="sm" onClick={openNew}>
          <Plus className="size-3.5" />
          New Profile
        </Button>
      </div>

      <div className="flex-1 overflow-auto p-4">
        {profiles.length === 0 ? (
          <EmptyState
            icon={Cpu}
            title="No profiles"
            description="Create a reusable processing profile to get started"
          />
        ) : (
          <div className="space-y-2">
            {profiles.map((profile) => (
              <div
                key={profile.name}
                className="group flex items-start gap-3 rounded-lg border border-border p-3"
              >
                <Cpu className="mt-0.5 size-4 text-muted-foreground" />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-medium">{profile.name}</p>
                    {(profile.mandatory_instructions?.length ?? 0) > 0 ? (
                      <Badge variant="info" className="text-[10px]">
                        {profile.mandatory_instructions?.length} rule{profile.mandatory_instructions?.length !== 1 ? "s" : ""}
                      </Badge>
                    ) : null}
                    {(profile.special_entity_types?.length ?? 0) > 0 ? (
                      <Badge variant="secondary" className="text-[10px]">
                        {profile.special_entity_types?.length} entity type
                        {profile.special_entity_types?.length !== 1 ? "s" : ""}
                      </Badge>
                    ) : null}
                  </div>
                  {profile.description ? (
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {profile.description}
                    </p>
                  ) : null}
                  {profile.context_instructions ? (
                    <p className="mt-1 line-clamp-3 text-[10px] text-muted-foreground">
                      {profile.context_instructions}
                    </p>
                  ) : (
                    <p className="mt-1 text-[10px] italic text-muted-foreground">
                      No context instructions
                    </p>
                  )}
                </div>
                <div className="flex gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                  <Button variant="ghost" size="icon-sm" onClick={() => openEdit(profile)}>
                    <Edit2 className="size-3.5" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    onClick={() => deleteMutation.mutate(profile.name)}
                  >
                    <Trash2 className="size-3.5" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle className="text-sm">
              {isNew ? "Create" : "Edit"} Processing Profile
            </DialogTitle>
          </DialogHeader>

          <div className="space-y-4">
            <div className="space-y-1.5">
              <Input
                placeholder="Profile name"
                value={editProfile.name}
                onChange={(event) =>
                  setEditProfile({ ...editProfile, name: event.target.value })
                }
                disabled={!isNew}
              />
              <Textarea
                placeholder="Short description"
                value={editProfile.description || ""}
                onChange={(event) =>
                  setEditProfile({ ...editProfile, description: event.target.value })
                }
                rows={2}
              />
            </div>

              <Textarea
                placeholder="Context for the kinds of documents this reusable profile is for"
                value={editProfile.context_instructions || ""}
                onChange={(event) =>
                  setEditProfile({
                    ...editProfile,
                    context_instructions: event.target.value,
                  })
                }
                className="min-h-[180px]"
              />

            <InstructionListEditor
              label="Mandatory Instructions"
              description="Add one-line extraction rules that should be treated as mandatory whenever this reusable profile is used."
              instructions={editProfile.mandatory_instructions ?? []}
              onChange={(instructions) =>
                setEditProfile((current) => ({
                  ...current,
                  mandatory_instructions: instructions,
                }))
              }
              placeholder="Treat each transaction row as a separate event."
              badgeVariant="info"
            />

            <div className="space-y-2 rounded-lg border border-border p-4">
              <p className="text-xs font-medium text-muted-foreground">
                Special Entity Types
              </p>

              {(editProfile.special_entity_types?.length ?? 0) > 0 ? (
                <div className="flex flex-wrap gap-1.5">
                  {editProfile.special_entity_types?.map((entity, index) => (
                    <Badge key={`${entity.name}-${index}`} variant="secondary" className="gap-1 pr-1">
                      <span>{entity.name}</span>
                      {entity.description ? (
                        <span className="text-muted-foreground" title={entity.description}>
                          *
                        </span>
                      ) : null}
                      <button
                        type="button"
                        onClick={() => removeEntityType(index)}
                        className="ml-0.5 rounded-full p-0.5 transition-colors hover:bg-muted"
                        aria-label={`Remove ${entity.name}`}
                      >
                        <X className="size-2.5" />
                      </button>
                    </Badge>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-muted-foreground">
                  No entity-type hints configured.
                </p>
              )}

              <div className="grid gap-2 md:grid-cols-[1fr_1fr_auto]">
                <Input
                  placeholder="Entity type name"
                  value={newEntityName}
                  onChange={(event) => setNewEntityName(event.target.value)}
                  className="h-8 text-xs"
                />
                <Input
                  placeholder="Description (optional)"
                  value={newEntityDesc}
                  onChange={(event) => setNewEntityDesc(event.target.value)}
                  className="h-8 text-xs"
                />
                <Button
                  variant="outline"
                  size="sm"
                  onClick={addEntityType}
                  disabled={!newEntityName.trim()}
                >
                  <Plus className="size-3.5" />
                  Add
                </Button>
              </div>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setEditOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={() =>
                saveMutation.mutate({
                  ...editProfile,
                  description: editProfile.description?.trim() || undefined,
                  context_instructions: editProfile.context_instructions?.trim() || undefined,
                  mandatory_instructions: editProfile.mandatory_instructions ?? [],
                  special_entity_types: editProfile.special_entity_types ?? [],
                })
              }
              disabled={!editProfile.name.trim() || saveMutation.isPending}
            >
              <Save className="size-3.5" />
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
