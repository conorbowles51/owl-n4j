import { Link, Outlet } from "react-router-dom"
import { PageHeader } from "@/components/ui/page-header"
import { isAdminUser } from "@/features/auth/auth.types"
import { useAuthStore } from "@/features/auth/hooks/use-auth"

export function AdminLayout() {
  // ProtectedRoute has the profile before it renders this, so the role is known on the first paint.
  const user = useAuthStore((state) => state.user)

  if (!isAdminUser(user)) {
    return (
      <main className="flex h-full items-center justify-center bg-background p-6">
        <section className="w-full max-w-md space-y-3 rounded border bg-card p-6">
          <h1 className="text-lg font-semibold">Administrators only</h1>
          <p>Your account cannot open this page. Ask an administrator if you need it.</p>
          <Link className="underline" to="/cases">
            Back to cases
          </Link>
        </section>
      </main>
    )
  }

  return (
    <div className="flex h-full flex-col bg-background">
      <div className="border-b border-border bg-card px-6 py-3">
        <PageHeader title="Administration" />
      </div>
      <div className="flex-1 overflow-auto p-6">
        <Outlet />
      </div>
    </div>
  )
}
