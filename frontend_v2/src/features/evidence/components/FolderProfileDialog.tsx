import { useState, useEffect } from "react"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { profilesAPI, type Profile } from "@/features/admin/api"

interface FolderProfileDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  caseId: string
  folderPath?: string
  editingProfile?: string
  onSaved?: () => void
}

export function FolderProfileDialog({
  open,
  onOpenChange,
  caseId,
  folderPath,
  editingProfile,
  onSaved,
}: FolderProfileDialogProps) {
  const [profiles, setProfiles] = useState<Profile[]>([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [profileName, setProfileName] = useState("")
  const [description, setDescription] = useState("")
  const [instructions, setInstructions] = useState("")
  const [selectedProfile, setSelectedProfile] = useState("")
  const [mode, setMode] = useState<"new" | "existing">("new")

  useEffect(() => {
    if (open) {
      setLoading(true)
      profilesAPI.list().then((data) => {
        setProfiles(data)
        setLoading(false)
      }).catch(() => setLoading(false))

      if (editingProfile) {
        profilesAPI.get(editingProfile).then((profile) => {
          setProfileName(profile.name)
          setDescription(profile.description ?? "")
          setMode("new")
        }).catch(() => {})
      }
    }
  }, [open, editingProfile])

  const handleSave = async () => {
    setSaving(true)
    try {
      if (mode === "new") {
        await profilesAPI.save({
          name: profileName,
          description,
          settings: { processing_instructions: instructions, folder_path: folderPath, case_id: caseId },
        })
      }
      onSaved?.()
      onOpenChange(false)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {editingProfile ? "Edit Profile" : "Configure Processing"}
          </DialogTitle>
        </DialogHeader>

        {loading ? (
          <div className="flex justify-center py-8">
            <LoadingSpinner />
          </div>
        ) : (
          <div className="space-y-4">
            <div className="flex gap-2">
              <Button
                variant={mode === "new" ? "primary" : "outline"}
                size="sm"
                onClick={() => setMode("new")}
              >
                New Profile
              </Button>
              <Button
                variant={mode === "existing" ? "primary" : "outline"}
                size="sm"
                onClick={() => setMode("existing")}
              >
                Use Existing
              </Button>
            </div>

            {mode === "existing" ? (
              <Select value={selectedProfile} onValueChange={setSelectedProfile}>
                <SelectTrigger>
                  <SelectValue placeholder="Select a profile..." />
                </SelectTrigger>
                <SelectContent>
                  {profiles.map((p) => (
                    <SelectItem key={p.name} value={p.name}>
                      {p.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <>
                <div>
                  <label className="mb-1 block text-xs font-medium text-foreground">
                    Profile Name
                  </label>
                  <Input
                    value={profileName}
                    onChange={(e) => setProfileName(e.target.value)}
                    placeholder="e.g. Wiretap Analysis"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-foreground">
                    Description
                  </label>
                  <Input
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="Brief description of this profile"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-foreground">
                    Processing Instructions
                  </label>
                  <Textarea
                    value={instructions}
                    onChange={(e) => setInstructions(e.target.value)}
                    placeholder="Describe how files in this folder should be processed..."
                    className="min-h-[120px]"
                  />
                </div>
              </>
            )}

            {folderPath && (
              <p className="text-xs text-muted-foreground">
                Folder: <span className="font-mono">{folderPath}</span>
              </p>
            )}
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={handleSave}
            disabled={saving || (mode === "new" && !profileName)}
          >
            {saving ? "Saving..." : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
