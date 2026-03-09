import { useState } from "react"
import { Cpu, Plus, Trash2, Edit2, Save } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Badge } from "@/components/ui/badge"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"
import { EmptyState } from "@/components/ui/empty-state"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { profilesAPI, type Profile } from "../api"

export function ProfileManagementPage() {
  const queryClient = useQueryClient()
  const [editOpen, setEditOpen] = useState(false)
  const [editProfile, setEditProfile] = useState<Profile>({
    name: "",
    provider: "",
    model: "",
    description: "",
  })
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
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (name: string) => profilesAPI.delete(name),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["profiles"] }),
  })

  const openNew = () => {
    setEditProfile({ name: "", provider: "", model: "", description: "" })
    setIsNew(true)
    setEditOpen(true)
  }

  const openEdit = (profile: Profile) => {
    setEditProfile({ ...profile })
    setIsNew(false)
    setEditOpen(true)
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
            description="Create a processing profile to get started"
          />
        ) : (
          <div className="space-y-2">
            {profiles.map((profile) => (
              <div
                key={profile.name}
                className="group flex items-center gap-3 rounded-lg border border-border p-3"
              >
                <Cpu className="size-4 text-muted-foreground" />
                <div className="flex-1">
                  <p className="text-sm font-medium">{profile.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {profile.provider} / {profile.model}
                  </p>
                  {profile.description && (
                    <p className="mt-0.5 text-[10px] text-muted-foreground">
                      {profile.description}
                    </p>
                  )}
                </div>
                <div className="flex gap-1 opacity-0 group-hover:opacity-100">
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
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle className="text-sm">
              {isNew ? "Create" : "Edit"} Profile
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <Input
              placeholder="Profile name"
              value={editProfile.name}
              onChange={(e) => setEditProfile({ ...editProfile, name: e.target.value })}
              disabled={!isNew}
            />
            <Input
              placeholder="Provider (e.g. openai, anthropic)"
              value={editProfile.provider || ""}
              onChange={(e) => setEditProfile({ ...editProfile, provider: e.target.value })}
            />
            <Input
              placeholder="Model (e.g. gpt-4, claude-3)"
              value={editProfile.model || ""}
              onChange={(e) => setEditProfile({ ...editProfile, model: e.target.value })}
            />
            <Textarea
              placeholder="Description"
              value={editProfile.description || ""}
              onChange={(e) => setEditProfile({ ...editProfile, description: e.target.value })}
              rows={2}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setEditOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={() => saveMutation.mutate(editProfile)}
              disabled={!editProfile.name || saveMutation.isPending}
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
