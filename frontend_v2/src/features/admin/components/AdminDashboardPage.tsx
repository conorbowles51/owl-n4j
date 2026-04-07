import { useQuery } from "@tanstack/react-query"
import { Users, Cpu, FileText, Activity } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { authAPI } from "@/features/auth/api"
import { profilesAPI } from "../api"

export function AdminDashboardPage() {
  const { data: users = [], isLoading: usersLoading } = useQuery({
    queryKey: ["users"],
    queryFn: () => authAPI.getUsers(),
  })

  const { data: profiles = [], isLoading: profilesLoading } = useQuery({
    queryKey: ["profiles"],
    queryFn: () => profilesAPI.list(),
  })

  if (usersLoading || profilesLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  const stats = [
    { label: "Users", value: users.length, icon: Users, color: "text-blue-500" },
    { label: "Profiles", value: profiles.length, icon: Cpu, color: "text-amber-500" },
    { label: "Active Tasks", value: 0, icon: Activity, color: "text-emerald-500" },
    { label: "System Logs", value: "—", icon: FileText, color: "text-slate-400" },
  ]

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-lg font-semibold">Admin Dashboard</h1>
        <p className="text-xs text-muted-foreground">
          System overview and management
        </p>
      </div>

      <div className="grid grid-cols-4 gap-4">
        {stats.map((stat) => (
          <Card key={stat.label}>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-xs font-medium text-muted-foreground">
                {stat.label}
              </CardTitle>
              <stat.icon className={`size-4 ${stat.color}`} />
            </CardHeader>
            <CardContent>
              <span className="text-2xl font-bold">{stat.value}</span>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Recent Users</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {users.slice(0, 5).map((user) => (
                <div
                  key={user.username}
                  className="flex items-center justify-between rounded-md px-2 py-1.5 hover:bg-muted/30"
                >
                  <div>
                    <p className="text-xs font-medium">{user.name}</p>
                    <p className="text-[10px] text-muted-foreground">
                      {user.username}
                    </p>
                  </div>
                  {user.role && (
                    <span className="rounded-full bg-muted px-2 py-0.5 text-[10px]">
                      {user.role}
                    </span>
                  )}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Active Profiles</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {profiles.slice(0, 5).map((p) => (
                <div
                  key={p.name}
                  className="flex items-center justify-between rounded-md px-2 py-1.5 hover:bg-muted/30"
                >
                  <div>
                    <p className="text-xs font-medium">{p.name}</p>
                    <p className="text-[10px] text-muted-foreground">
                      {(p.special_entity_types?.length ?? 0) > 0
                        ? `${p.special_entity_types?.length} entity type${p.special_entity_types?.length !== 1 ? "s" : ""}`
                        : "No entity types"}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
