import { Outlet, useParams, NavLink } from "react-router-dom"
import {
  Network,
  Clock,
  Map,
  TableProperties,
  DollarSign,
} from "lucide-react"
import { cn } from "@/lib/cn"
import { ErrorBoundary } from "@/components/ui/error-boundary"

const viewTabs = [
  { label: "Graph", icon: Network, path: "graph" },
  { label: "Timeline", icon: Clock, path: "timeline" },
  { label: "Map", icon: Map, path: "map" },
  { label: "Table", icon: TableProperties, path: "table" },
  { label: "Financial", icon: DollarSign, path: "financial" },
]

export function CaseLayout() {
  const { id } = useParams()

  return (
    <div className="flex h-full flex-col">
      {/* View mode tabs */}
      <div className="flex items-center gap-1 border-b border-border px-4 py-1">
        {viewTabs.map((tab) => (
          <NavLink
            key={tab.path}
            to={`/cases/${id}/${tab.path}`}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
                "text-muted-foreground hover:bg-muted hover:text-foreground",
                isActive && "bg-muted text-foreground"
              )
            }
          >
            <tab.icon className="size-3.5" />
            {tab.label}
          </NavLink>
        ))}
      </div>

      {/* View content */}
      <div className="flex-1 overflow-auto">
        <ErrorBoundary level="page">
          <Outlet />
        </ErrorBoundary>
      </div>
    </div>
  )
}
