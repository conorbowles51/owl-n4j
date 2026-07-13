import type { ReactNode } from "react"
import { Link, useLocation, useParams } from "react-router-dom"
import {
  FolderOpen,
  Network,
  Clock,
  Map,
  TableProperties,
  DollarSign,
  FileText,
  MessageSquare,
  Bot,
  Briefcase,
  ClipboardList,
  Settings,
  Smartphone,
  UserRoundSearch,
  Users,
  Sliders,
  ShieldCheck,
  ChevronLeft,
  ChevronRight,
  CloudDownload,
  type LucideIcon,
} from "lucide-react"
import { cn } from "@/lib/cn"
import { useAppStore } from "@/stores/app.store"
import { Button } from "@/components/ui/button"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"

interface NavItem {
  label: string
  icon: LucideIcon
  to: string
  end?: boolean
  shortcut?: string
}

const mainNav: NavItem[] = [
  { label: "Cases", icon: FolderOpen, to: "/cases", end: true },
  { label: "Triage", icon: ShieldCheck, to: "/triage", end: true },
]

function getCaseInvestigationNav(caseId: string): NavItem[] {
  return [
    { label: "Graph", icon: Network, to: `/cases/${caseId}/graph`, shortcut: "1" },
    { label: "Timeline", icon: Clock, to: `/cases/${caseId}/timeline`, shortcut: "2" },
    { label: "Map", icon: Map, to: `/cases/${caseId}/map`, shortcut: "3" },
    { label: "Table", icon: TableProperties, to: `/cases/${caseId}/table`, shortcut: "4" },
    { label: "Financial", icon: DollarSign, to: `/cases/${caseId}/financial`, shortcut: "5" },
    { label: "Cellebrite", icon: Smartphone, to: `/cases/${caseId}/cellebrite`, shortcut: "6" },
    { label: "Profiles", icon: UserRoundSearch, to: `/cases/${caseId}/profiles`, shortcut: "7" },
    { label: "Evidence", icon: FileText, to: `/cases/${caseId}/evidence`, shortcut: "8" },
  ]
}

function getCaseAiNav(caseId: string): NavItem[] {
  return [
    { label: "Chat", icon: MessageSquare, to: `/cases/${caseId}/chat` },
    { label: "Agent", icon: Bot, to: `/cases/${caseId}/agent` },
  ]
}

function getCaseWorkspaceNav(caseId: string): NavItem[] {
  return [
    { label: "Workspace", icon: Briefcase, to: `/cases/${caseId}/workspace` },
    { label: "Reports", icon: ClipboardList, to: `/cases/${caseId}/reports` },
  ]
}

const adminNav: NavItem[] = [
  { label: "AI Costs", icon: DollarSign, to: "/admin/ai-costs" },
  { label: "Updates", icon: CloudDownload, to: "/admin/updates" },
  { label: "Users", icon: Users, to: "/admin/users" },
  { label: "Profiles", icon: Sliders, to: "/admin/profiles" },
]

const settingsItem: NavItem = {
  label: "Settings",
  icon: Settings,
  to: "/settings",
  end: true,
}

function ShortcutHint({ value, active = false }: { value: string; active?: boolean }) {
  return (
    <kbd
      className={cn(
        "ml-auto rounded px-1.5 py-0.5 font-mono text-[10px] font-medium tabular-nums",
        active
          ? "bg-white/80 text-amber-700 dark:bg-slate-950/50 dark:text-amber-300"
          : "text-slate-400 dark:text-slate-500"
      )}
    >
      Ctrl+{value}
    </kbd>
  )
}

function SidebarLink({
  item,
  expanded,
  active,
}: {
  item: NavItem
  expanded: boolean
  active: boolean
}) {
  const link = (
    <Link
      to={item.to}
      aria-current={active ? "page" : undefined}
      aria-label={!expanded ? item.label : undefined}
      className={cn(
        "group relative flex items-center rounded-lg text-sm font-medium outline-none",
        "transition-[background-color,color,box-shadow,transform] duration-150 ease-[cubic-bezier(0.2,0,0,1)]",
        "focus-visible:ring-2 focus-visible:ring-amber-500/35 focus-visible:ring-offset-2 focus-visible:ring-offset-white active:scale-[0.96]",
        "dark:focus-visible:ring-amber-400/40 dark:focus-visible:ring-offset-slate-950",
        expanded ? "h-9 w-full gap-3 px-3" : "mx-auto h-9 w-9 justify-center px-0",
        "text-slate-500 hover:text-slate-950 dark:text-slate-400 dark:hover:text-slate-50",
        expanded
          ? "hover:bg-slate-100/75 dark:hover:bg-slate-800/80"
          : "hover:bg-slate-100/80 dark:hover:bg-slate-800/80",
        active &&
          (expanded
            ? "bg-amber-50 text-slate-950 shadow-[inset_0_0_0_1px_rgba(212,146,10,0.16)] before:absolute before:left-1.5 before:top-1/2 before:h-5 before:w-0.5 before:-translate-y-1/2 before:rounded-full before:bg-amber-500 dark:bg-amber-500/10 dark:text-slate-50 dark:shadow-[inset_0_0_0_1px_rgba(212,146,10,0.24)]"
            : "bg-slate-900 text-white shadow-[0_10px_20px_-12px_rgba(17,24,39,0.9)] dark:bg-slate-100 dark:text-slate-950")
      )}
    >
      <item.icon
        className={cn(
          "size-4 shrink-0 transition-[color,transform] duration-150",
          !expanded && "size-[17px]",
          active && expanded && "text-amber-600 dark:text-amber-400",
          !active && "group-hover:scale-105"
        )}
      />
      {expanded && (
        <span className="min-w-0 flex-1 truncate">{item.label}</span>
      )}
      {expanded && item.shortcut && (
        <ShortcutHint value={item.shortcut} active={active} />
      )}
    </Link>
  )

  if (!expanded) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>{link}</TooltipTrigger>
        <TooltipContent side="right" sideOffset={10}>
          <span className="flex items-center gap-2">
            <span>{item.label}</span>
            {item.shortcut && (
              <kbd className="rounded bg-background/15 px-1.5 py-0.5 font-mono text-[10px] text-background/80">
                Ctrl+{item.shortcut}
              </kbd>
            )}
          </span>
        </TooltipContent>
      </Tooltip>
    )
  }

  return link
}

function SidebarSection({
  label,
  expanded,
  separated = false,
  children,
}: {
  label: string
  expanded: boolean
  separated?: boolean
  children: ReactNode
}) {
  return (
    <section
      className={cn(
        expanded ? "space-y-0.5" : "space-y-1",
        separated && (expanded ? "mt-4" : "mt-3")
      )}
      aria-label={label}
    >
      {expanded ? (
        <p className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500">
          {label}
        </p>
      ) : (
        separated && (
          <div
            className="mx-auto mb-2 h-px w-6 bg-slate-200 dark:bg-slate-800"
            aria-hidden="true"
          />
        )
      )}
      {children}
    </section>
  )
}

function isItemActive(pathname: string, item: NavItem) {
  if (item.end) {
    return pathname === item.to
  }

  return pathname === item.to || pathname.startsWith(`${item.to}/`)
}

function LogoMark({ expanded }: { expanded: boolean }) {
  const mark = (
    <Link
      to="/cases"
      aria-label="Loupe cases"
      className={cn(
        "group flex min-w-0 items-center rounded-lg outline-none",
        "transition-[background-color,box-shadow,transform] duration-150 ease-[cubic-bezier(0.2,0,0,1)] active:scale-[0.96]",
        "focus-visible:ring-2 focus-visible:ring-amber-500/35 focus-visible:ring-offset-2 focus-visible:ring-offset-white",
        "dark:focus-visible:ring-amber-400/40 dark:focus-visible:ring-offset-slate-950",
        expanded ? "h-10 w-full gap-2.5 px-2" : "mx-auto h-10 w-10 justify-center"
      )}
    >
      <span
        className="relative flex size-8 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-white shadow-[0_8px_18px_-14px_rgba(17,24,39,0.65)] dark:border-slate-700 dark:bg-slate-900"
        aria-hidden="true"
      >
        <span className="size-[18px] rounded-full border-[3px] border-amber-500 transition-[transform,border-color] duration-150 group-hover:scale-105 dark:border-amber-400" />
        <span className="absolute size-1.5 rounded-full bg-slate-950 dark:bg-slate-50" />
      </span>
      {expanded && (
        <span className="min-w-0 text-[15px] font-black leading-none tracking-[0.18em] text-slate-950 dark:text-slate-50">
          Loupe
        </span>
      )}
    </Link>
  )

  if (expanded) {
    return mark
  }

  return (
    <Tooltip>
      <TooltipTrigger asChild>{mark}</TooltipTrigger>
      <TooltipContent side="right" sideOffset={10}>
        Loupe
      </TooltipContent>
    </Tooltip>
  )
}

export function AppSidebar() {
  const { id: caseId } = useParams()
  const { pathname } = useLocation()
  const { sidebarExpanded, toggleSidebar } = useAppStore()
  const user = useAuthStore((s) => s.user)
  const role = user?.global_role ?? user?.role
  const canSeeAdmin = role === "admin" || role === "super_admin"

  const toggleButton = (
    <Button
      variant="ghost"
      size={sidebarExpanded ? "default" : "icon"}
      className={cn(
        "mt-1 w-full transition-[background-color,color,box-shadow,transform] active:scale-[0.96]",
        sidebarExpanded
          ? "justify-start text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100"
          : "mx-auto h-10 w-10 justify-center"
      )}
      onClick={toggleSidebar}
      aria-label={sidebarExpanded ? "Collapse sidebar" : "Expand sidebar"}
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
  )

  return (
    <aside
      className={cn(
        "flex h-screen shrink-0 flex-col border-r border-slate-200/80 shadow-[1px_0_0_rgba(17,24,39,0.02)]",
        "bg-[linear-gradient(180deg,#fff_0%,#fbfcfd_45%,#f8fafc_100%)] transition-[width] duration-200 ease-[cubic-bezier(0.2,0,0,1)]",
        "dark:border-slate-800 dark:bg-[linear-gradient(180deg,#0b0f1a_0%,#0e1422_100%)]",
        sidebarExpanded ? "w-60" : "w-16"
      )}
    >
      <div
        className={cn(
          "flex items-center border-b border-slate-200/80 dark:border-slate-800",
          sidebarExpanded ? "h-14 px-3" : "h-14 px-2"
        )}
      >
        <LogoMark expanded={sidebarExpanded} />
      </div>

      <nav className="flex-1 space-y-1 overflow-y-auto px-2 py-3">
        <SidebarSection label="Investigation" expanded={sidebarExpanded}>
          {mainNav.map((item) => (
            <SidebarLink
              key={item.to}
              item={item}
              expanded={sidebarExpanded}
              active={isItemActive(pathname, item)}
            />
          ))}
        </SidebarSection>

        {caseId && (
          <SidebarSection label="Active Case" expanded={sidebarExpanded} separated>
            {getCaseInvestigationNav(caseId).map((item) => (
              <SidebarLink
                key={item.to}
                item={item}
                expanded={sidebarExpanded}
                active={isItemActive(pathname, item)}
              />
            ))}
          </SidebarSection>
        )}

        {caseId && (
          <SidebarSection label="AI" expanded={sidebarExpanded} separated>
            {getCaseAiNav(caseId).map((item) => (
              <SidebarLink
                key={item.to}
                item={item}
                expanded={sidebarExpanded}
                active={isItemActive(pathname, item)}
              />
            ))}
          </SidebarSection>
        )}

        {caseId && (
          <SidebarSection label="Workspace" expanded={sidebarExpanded} separated>
            {getCaseWorkspaceNav(caseId).map((item) => (
              <SidebarLink
                key={item.to}
                item={item}
                expanded={sidebarExpanded}
                active={isItemActive(pathname, item)}
              />
            ))}
          </SidebarSection>
        )}

        {canSeeAdmin && (
          <SidebarSection label="Admin" expanded={sidebarExpanded} separated>
            {adminNav.map((item) => (
              <SidebarLink
                key={item.to}
                item={item}
                expanded={sidebarExpanded}
                active={isItemActive(pathname, item)}
              />
            ))}
          </SidebarSection>
        )}
      </nav>

      <div className="border-t border-slate-200/80 p-2 dark:border-slate-800">
        <SidebarLink
          item={settingsItem}
          expanded={sidebarExpanded}
          active={isItemActive(pathname, settingsItem)}
        />
        {sidebarExpanded ? (
          toggleButton
        ) : (
          <Tooltip>
            <TooltipTrigger asChild>{toggleButton}</TooltipTrigger>
            <TooltipContent side="right" sideOffset={10}>
              Expand sidebar
            </TooltipContent>
          </Tooltip>
        )}
      </div>
    </aside>
  )
}
