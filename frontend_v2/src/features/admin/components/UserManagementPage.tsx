import { useState } from "react"
import { Users, Plus, Trash2, Shield } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
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
import { authAPI } from "@/features/auth/api"
import { fetchAPI } from "@/lib/api-client"

export function UserManagementPage() {
  const queryClient = useQueryClient()
  const [createOpen, setCreateOpen] = useState(false)
  const [search, setSearch] = useState("")
  const [newUser, setNewUser] = useState({ username: "", name: "", password: "", role: "" })

  const { data: users = [], isLoading } = useQuery({
    queryKey: ["users"],
    queryFn: () => authAPI.getUsers(),
  })

  const createMutation = useMutation({
    mutationFn: (data: { username: string; name: string; password: string; role?: string }) =>
      fetchAPI<void>("/api/users", { method: "POST", body: data }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] })
      setCreateOpen(false)
      setNewUser({ username: "", name: "", password: "", role: "" })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (username: string) =>
      fetchAPI<void>(`/api/users/${encodeURIComponent(username)}`, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["users"] }),
  })

  const filtered = users.filter(
    (u) =>
      u.name.toLowerCase().includes(search.toLowerCase()) ||
      u.username.toLowerCase().includes(search.toLowerCase())
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
                key={user.username}
                className="group flex items-center gap-3 rounded-lg border border-border p-3"
              >
                <div className="flex size-8 items-center justify-center rounded-full bg-amber-500/10">
                  <Users className="size-4 text-amber-500" />
                </div>
                <div className="flex-1">
                  <p className="text-sm font-medium">{user.name}</p>
                  <p className="text-xs text-muted-foreground">{user.username}</p>
                </div>
                {user.role && (
                  <Badge variant={user.role === "super_admin" ? "amber" : "outline"}>
                    {user.role === "super_admin" ? (
                      <><Shield className="mr-1 size-3" />Admin</>
                    ) : (
                      user.role
                    )}
                  </Badge>
                )}
                <Button
                  variant="ghost"
                  size="icon-sm"
                  className="opacity-0 group-hover:opacity-100"
                  onClick={() => deleteMutation.mutate(user.username)}
                >
                  <Trash2 className="size-3.5" />
                </Button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Create user dialog */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle className="text-sm">Create User</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <Input
              placeholder="Username"
              value={newUser.username}
              onChange={(e) => setNewUser({ ...newUser, username: e.target.value })}
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
            <Input
              placeholder="Role (optional)"
              value={newUser.role}
              onChange={(e) => setNewUser({ ...newUser, role: e.target.value })}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setCreateOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={() => createMutation.mutate(newUser)}
              disabled={!newUser.username || !newUser.name || !newUser.password || createMutation.isPending}
            >
              Create
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
