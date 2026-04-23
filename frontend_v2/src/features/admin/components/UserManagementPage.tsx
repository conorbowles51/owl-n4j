import { useMemo, useState } from "react"
import { Users, Plus, Shield } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
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
import { authAPI } from "@/features/auth/api"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import { fetchAPI } from "@/lib/api-client"
import { toast } from "sonner"

type UserRole = "super_admin" | "admin" | "user" | "guest"

const ROLE_LABELS: Record<UserRole, string> = {
  super_admin: "Super Admin",
  admin: "Admin",
  user: "User",
  guest: "Guest",
}

function getRoleOptions(currentRole?: string): UserRole[] {
  if (currentRole === "super_admin") {
    return ["super_admin", "admin", "user", "guest"]
  }

  return ["user", "guest"]
}

export function UserManagementPage() {
  const queryClient = useQueryClient()
  const currentUser = useAuthStore((state) => state.user)
  const [createOpen, setCreateOpen] = useState(false)
  const [search, setSearch] = useState("")
  const availableRoles = useMemo(
    () => getRoleOptions(currentUser?.global_role ?? currentUser?.role ?? undefined),
    [currentUser]
  )
  const defaultRole = availableRoles[0] ?? "user"
  const [newUser, setNewUser] = useState<{
    email: string
    name: string
    password: string
    role: UserRole
  }>({
    email: "",
    name: "",
    password: "",
    role: defaultRole,
  })

  const resetCreateForm = () => {
    setNewUser({ email: "", name: "", password: "", role: defaultRole })
    createMutation.reset()
  }

  const { data: users = [], isLoading } = useQuery({
    queryKey: ["users"],
    queryFn: () => authAPI.getUsers(),
  })

  const createMutation = useMutation({
    mutationFn: (data: { email: string; name: string; password: string; role: UserRole }) =>
      fetchAPI<void>("/api/users", {
        method: "POST",
        body: {
          email: data.email.trim(),
          name: data.name.trim(),
          password: data.password,
          role: data.role,
        },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] })
      setCreateOpen(false)
      resetCreateForm()
    },
  })

  const updateRoleMutation = useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: UserRole }) =>
      fetchAPI<void>(`/api/users/${encodeURIComponent(userId)}`, {
        method: "PATCH",
        body: { role },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] })
      toast.success("Role updated")
    },
    onError: (error: unknown) => {
      const message = error instanceof Error ? error.message : "Failed to update role"
      toast.error(message)
    },
  })

  const filtered = users.filter(
    (u) =>
      u.name.toLowerCase().includes(search.toLowerCase()) ||
      (u.email ?? u.username).toLowerCase().includes(search.toLowerCase())
  )

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
        <Users className="size-4 text-amber-500" />
        <span className="text-sm font-semibold">User Management</span>
        <div className="flex-1" />
        <Input
          placeholder="Search users..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-xs"
        />
        <Button variant="primary" size="sm" onClick={() => setCreateOpen(true)}>
          <Plus className="size-3.5" />
          Add User
        </Button>
      </div>

      <div className="flex-1 overflow-auto p-4">
        {filtered.length === 0 ? (
          <EmptyState
            icon={Users}
            title="No users found"
            description={search ? "Try a different search" : "Create your first user"}
          />
        ) : (
          <div className="space-y-2">
            {filtered.map((user) => (
              <div
                key={user.id ?? user.username}
                className="group flex items-center gap-3 rounded-lg border border-border p-3"
              >
                <div className="flex size-8 items-center justify-center rounded-full bg-amber-500/10">
                  <Users className="size-4 text-amber-500" />
                </div>
                <div className="flex-1">
                  <p className="text-sm font-medium">{user.name}</p>
                  <p className="text-xs text-muted-foreground">{user.email ?? user.username}</p>
                </div>
                {(() => {
                  const role = (user.global_role ?? user.role) as UserRole | undefined
                  const userId = user.id ?? user.username
                  const canEdit = !!role && availableRoles.includes(role)
                  if (!canEdit) {
                    return role ? (
                      <Badge variant={role === "super_admin" ? "amber" : "outline"}>
                        {role === "super_admin" ? (
                          <><Shield className="mr-1 size-3" />Super Admin</>
                        ) : (
                          ROLE_LABELS[role] ?? role
                        )}
                      </Badge>
                    ) : null
                  }
                  return (
                    <Select
                      value={role}
                      onValueChange={(value) =>
                        updateRoleMutation.mutate({
                          userId,
                          role: value as UserRole,
                        })
                      }
                      disabled={updateRoleMutation.isPending}
                    >
                      <SelectTrigger className="h-7 w-[130px] text-xs">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {availableRoles.map((r) => (
                          <SelectItem key={r} value={r}>
                            {ROLE_LABELS[r]}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  )
                })()}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Create user dialog */}
      <Dialog
        open={createOpen}
        onOpenChange={(open) => {
          setCreateOpen(open)
          if (!open) {
            resetCreateForm()
          }
        }}
      >
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle className="text-sm">Create User</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <Input
              placeholder="Email"
              value={newUser.email}
              onChange={(e) => setNewUser({ ...newUser, email: e.target.value })}
            />
            <Input
              placeholder="Display name"
              value={newUser.name}
              onChange={(e) => setNewUser({ ...newUser, name: e.target.value })}
            />
            <Input
              type="password"
              placeholder="Password"
              value={newUser.password}
              onChange={(e) => setNewUser({ ...newUser, password: e.target.value })}
            />
            <Select
              value={newUser.role}
              onValueChange={(value) =>
                setNewUser({ ...newUser, role: value as UserRole })
              }
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder="Select role" />
              </SelectTrigger>
              <SelectContent>
                {availableRoles.map((role) => (
                  <SelectItem key={role} value={role}>
                    {ROLE_LABELS[role]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {createMutation.error instanceof Error && (
              <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
                {createMutation.error.message}
              </div>
            )}
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setCreateOpen(false)
                resetCreateForm()
              }}
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={() => createMutation.mutate(newUser)}
              disabled={!newUser.email || !newUser.name || !newUser.password || createMutation.isPending}
            >
              Create
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
