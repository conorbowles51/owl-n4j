import { Outlet } from "react-router-dom"
import { PageHeader } from "@/components/ui/page-header"

export function AdminLayout() {
  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-border px-6 py-3">
        <PageHeader title="Administration" />
      </div>
      <div className="flex-1 overflow-auto p-6">
        <Outlet />
      </div>
    </div>
  )
}
