import { NavLink, useParams } from "react-router-dom"
import {
  FolderOpen,
  Network,
  Clock,
  Map,
  TableProperties,
  DollarSign,
  FileText,
  MessageSquare,
  Briefcase,
  ClipboardList,
  Settings,
  Users,
  Sliders,
  ChevronLeft,
  ChevronRight,
  type LucideIcon,
} from "lucide-react"
import { cn } from "@/lib/cn"
import { useAppStore } from "@/stores/app.store"
import { Button } from "@/components/ui/button"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"

interface NavItem {
  label: string
  icon: LucideIcon
  to: string
  shortcut?: string
}

const mainNav: NavItem[] = [
  { label: "Cases", icon: FolderOpen, to: "/cases" },
]

function getCaseNav(caseId: string): NavItem[] {
  return [
    { label: "Graph", icon: Network, to: `/cases/${caseId}/graph`, shortcut: "1" },
    { label: "Timeline", icon: Clock, to: `/cases/${caseId}/timeline`, shortcut: "2" },
    { label: "Map", icon: Map, to: `/cases/${caseId}/map`, shortcut: "3" },
    { label: "Table", icon: TableProperties, to: `/cases/${caseId}/table`, shortcut: "4" },
    { label: "Financial", icon: DollarSign, to: `/cases/${caseId}/financial`, shortcut: "5" },
    { label: "Evidence", icon: FileText, to: `/cases/${caseId}/evidence`, shortcut: "6" },
    { label: "Chat", icon: MessageSquare, to: `/cases/${caseId}/chat` },
    { label: "Workspace", icon: Briefcase, to: `/cases/${caseId}/workspace` },
    { label: "Reports", icon: ClipboardList, to: `/cases/${caseId}/reports` },
  ]
}

const adminNav: NavItem[] = [
  { label: "Users", icon: Users, to: "/admin/users" },
  { label: "Profiles", icon: Sliders, to: "/admin/profiles" },
]

function SidebarLink({
  item,
  expanded,
}: {
  item: NavItem
  expanded: boolean
}) {
  const link = (
    <NavLink
      to={item.to}
      className={({ isActive }) =>
        cn(
          "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
          "text-slate-400 hover:bg-slate-800 hover:text-slate-200",
          isActive &&
            "border-l-2 border-amber-500 bg-slate-800/50 text-slate-50",
          !expanded && "justify-center px-0"
        )
      }
    >
      <item.icon className="size-4 shrink-0" />
      {expanded && (
        <span className="flex-1 truncate">{item.label}</span>
      )}
      {expanded && item.shortcut && (
        <kbd className="text-[10px] text-slate-500">⌘{item.shortcut}</kbd>
      )}
    </NavLink>
  )

  if (!expanded) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>{link}</TooltipTrigger>
        <TooltipContent side="right" sideOffset={8}>
          {item.label}
          {item.shortcut && (
            <kbd className="ml-2 text-[10px] text-muted-foreground">
              ⌘{item.shortcut}
            </kbd>
          )}
        </TooltipContent>
      </Tooltip>
    )
  }

  return link
}

export function AppSidebar() {
  const { id: caseId } = useParams()
  const { sidebarExpanded, toggleSidebar } = useAppStore()

  return (
    <aside
      className={cn(
        "flex h-screen flex-col border-r border-border bg-slate-950 transition-all duration-200",
        sidebarExpanded ? "w-60" : "w-14"
      )}
    >
      {/* Logo */}
      <div
        className={cn(
          "flex h-12 items-center border-b border-border px-4",
          !sidebarExpanded && "justify-center px-0"
        )}
      >
        <span className="text-lg font-bold tracking-tight text-amber-500">
          {sidebarExpanded ? "OWL" : "O"}
        </span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 overflow-y-auto p-2">
        {/* Main */}
        <div className="space-y-0.5">
          {sidebarExpanded && (
            <p className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
              Investigation
            </p>
          )}
          {mainNav.map((item) => (
            <SidebarLink key={item.to} item={item} expanded={sidebarExpanded} />
          ))}
        </div>

        {/* Active Case */}
        {caseId && (
          <div className="mt-4 space-y-0.5">
            {sidebarExpanded && (
              <p className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                Active Case
              </p>
            )}
            {getCaseNav(caseId).map((item) => (
              <SidebarLink
                key={item.to}
                item={item}
                expanded={sidebarExpanded}
              />
            ))}
          </div>
        )}

        {/* Admin */}
        <div className="mt-4 space-y-0.5">
          {sidebarExpanded && (
            <p className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
              Admin
            </p>
          )}
          {adminNav.map((item) => (
            <SidebarLink key={item.to} item={item} expanded={sidebarExpanded} />
          ))}
        </div>
      </nav>

      {/* Bottom */}
      <div className="border-t border-border p-2">
        <SidebarLink
          item={{ label: "Settings", icon: Settings, to: "/settings" }}
          expanded={sidebarExpanded}
        />
        <Button
          variant="ghost"
          size={sidebarExpanded ? "default" : "icon"}
          className={cn("mt-1 w-full", !sidebarExpanded && "justify-center")}
          onClick={toggleSidebar}
        >
          {sidebarExpanded ? (
            <>
              <ChevronLeft className="size-4" />
              <span className="text-xs">Collapse</span>
            </>
          ) : (
            <ChevronRight className="size-4" />
          )}
        </Button>
      </div>
    </aside>
  )
}
