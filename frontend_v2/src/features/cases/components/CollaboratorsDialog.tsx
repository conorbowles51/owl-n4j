import { useState } from "react"
import {
  Users,
  UserPlus,
  Trash2,
  Crown,
  ChevronDown,
} from "lucide-react"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { EmptyState } from "@/components/ui/empty-state"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import {
  useCaseMembers,
  useAddCaseMember,
  useUpdateCaseMember,
  useRemoveCaseMember,
} from "../hooks/use-case-members"
import { useQuery } from "@tanstack/react-query"
import { authAPI } from "@/features/auth/api"
import { RoleBadge } from "./RoleBadge"

interface CollaboratorsDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  caseId: string
  canInvite: boolean
}

export function CollaboratorsDialog({
  open,
  onOpenChange,
  caseId,
  canInvite,
}: CollaboratorsDialogProps) {
  const { data: members, isLoading } = useCaseMembers(open ? caseId : undefined)
  const { data: allUsers } = useQuery({
    queryKey: ["users"],
    queryFn: () => authAPI.getUsers(),
    enabled: open && canInvite,
  })
  const addMember = useAddCaseMember(caseId)
  const updateMember = useUpdateCaseMember(caseId)
  const removeMember = useRemoveCaseMember(caseId)

  const [inviteSearch, setInviteSearch] = useState("")
  const [selectedUserId, setSelectedUserId] = useState("")
  const [selectedPreset, setSelectedPreset] = useState<"viewer" | "editor">("viewer")
  const [confirmRemoveId, setConfirmRemoveId] = useState<string | null>(null)

  const memberIds = new Set(members?.map((m) => m.user_id) ?? [])
  const availableUsers = (allUsers ?? []).filter(
    (u) =>
      !memberIds.has(u.id ?? "") &&
      (u.name.toLowerCase().includes(inviteSearch.toLowerCase()) ||
        (u.email ?? u.username).toLowerCase().includes(inviteSearch.toLowerCase()))
  )

  const handleInvite = () => {
    if (!selectedUserId) return
    addMember.mutate(
      { userId: selectedUserId, preset: selectedPreset },
      {
        onSuccess: () => {
          setSelectedUserId("")
          setInviteSearch("")
        },
      }
    )
  }

  const handleRemove = (userId: string) => {
    removeMember.mutate(userId, {
      onSuccess: () => setConfirmRemoveId(null),
    })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-sm">
            <Users className="size-4 text-amber-500" />
            Case Collaborators
          </DialogTitle>
        </DialogHeader>

        {isLoading ? (
          <div className="flex justify-center py-8">
            <LoadingSpinner />
          </div>
        ) : (
          <div className="space-y-4">
            {/* Member list */}
            <div className="space-y-1">
              {(members ?? []).length === 0 ? (
                <EmptyState
                  icon={Users}
                  title="No members"
                  className="py-4"
                />
              ) : (
                (members ?? []).map((member) => (
                  <div
                    key={member.user_id}
                    className="flex items-center gap-3 rounded-md border border-border px-3 py-2"
                  >
                    <div className="flex size-7 items-center justify-center rounded-full bg-amber-500/10">
                      {member.preset === "owner" ? (
                        <Crown className="size-3 text-amber-500" />
                      ) : (
                        <Users className="size-3 text-muted-foreground" />
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-xs font-medium">
                        {member.user_name}
                      </p>
                      <p className="truncate text-[10px] text-muted-foreground">
                        {member.user_email}
                      </p>
                    </div>

                    {member.preset === "owner" ? (
                      <RoleBadge role="owner" />
                    ) : (
                      <>
                        {canInvite && (
                          <select
                            value={member.preset}
                            onChange={(e) =>
                              updateMember.mutate({
                                userId: member.user_id,
                                preset: e.target.value as "viewer" | "editor",
                              })
                            }
                            className="h-6 rounded-md border border-border bg-background px-1.5 text-[10px]"
                          >
                            <option value="viewer">Viewer</option>
                            <option value="editor">Editor</option>
                          </select>
                        )}
                        {!canInvite && <RoleBadge role={member.preset} />}

                        {canInvite && (
                          <>
                            {confirmRemoveId === member.user_id ? (
                              <div className="flex gap-1">
                                <Button
                                  variant="danger"
                                  size="sm"
                                  className="h-6 text-[10px]"
                                  onClick={() => handleRemove(member.user_id)}
                                  disabled={removeMember.isPending}
                                >
                                  Confirm
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  className="h-6 text-[10px]"
                                  onClick={() => setConfirmRemoveId(null)}
                                >
                                  Cancel
                                </Button>
                              </div>
                            ) : (
                              <Button
                                variant="ghost"
                                size="icon-sm"
                                className="size-6"
                                onClick={() =>
                                  setConfirmRemoveId(member.user_id)
                                }
                              >
                                <Trash2 className="size-3" />
                              </Button>
                            )}
                          </>
                        )}
                      </>
                    )}
                  </div>
                ))
              )}
            </div>

            {/* Invite section */}
            {canInvite && (
              <div className="space-y-2 border-t border-border pt-3">
                <p className="text-xs font-semibold text-muted-foreground">
                  <UserPlus className="mr-1 inline size-3" />
                  Invite User
                </p>
                <div className="flex gap-2">
                  <Input
                    placeholder="Search users by name or email..."
                    value={inviteSearch}
                    onChange={(e) => setInviteSearch(e.target.value)}
                    className="h-7 flex-1 text-xs"
                  />
                  <select
                    value={selectedPreset}
                    onChange={(e) =>
                      setSelectedPreset(e.target.value as "viewer" | "editor")
                    }
                    className="h-7 rounded-md border border-border bg-background px-2 text-xs"
                  >
                    <option value="viewer">Viewer</option>
                    <option value="editor">Editor</option>
                  </select>
                  <Button
                    variant="primary"
                    size="sm"
                    className="h-7 text-xs"
                    onClick={handleInvite}
                    disabled={!selectedUserId || addMember.isPending}
                  >
                    Invite
                  </Button>
                </div>
                {inviteSearch && availableUsers.length > 0 && (
                  <div className="max-h-32 overflow-auto rounded-md border border-border">
                    {availableUsers.slice(0, 5).map((u) => (
                      <button
                        key={u.id ?? u.username}
                        onClick={() => {
                          setSelectedUserId(u.id ?? u.username)
                          setInviteSearch(u.name)
                        }}
                        className={`flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs transition-colors hover:bg-accent/50 ${
                          selectedUserId === (u.id ?? u.username)
                            ? "bg-amber-500/10"
                            : ""
                        }`}
                      >
                        <span className="font-medium">{u.name}</span>
                        <span className="text-muted-foreground">
                          {u.email ?? u.username}
                        </span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
