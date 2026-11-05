import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useEffect, useState, type ReactNode } from "react"
import { Link, useLocation, useParams } from "react-router-dom"
import { preloadRouteIntent } from "@/lib/route-preload"
import { phonesQuery } from "@/features/phones/phones-query"
import { HELP_PARAM, hideNewMarks, marksQuery, newMarksUntil } from "@/features/phones/marks"
import {
  Banknote,
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
  ContactRound,
  Users,
  Sliders,
  ShieldCheck,
  ChevronLeft,
  ChevronRight,
  CloudDownload,
  History,
  Gauge,
  type LucideIcon,
  Search as SearchIcon,
  ListChecks,
  CircleHelp,
} from "lucide-react"
import { cn } from "@/lib/cn"
import { LoupeLogo } from "@/components/brand/LoupeLogo"
import { useAppStore } from "@/stores/app.store"
import { Button } from "@/components/ui/button"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import { CaseLayerSwitcher } from "@/features/significant/components/CaseLayerSwitcher"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { useMediaQuery } from "@/hooks/use-media-query"
import { applySwitchesFromSearch, useSwitch } from "@/lib/ui-switches"

interface NavItem {
  label: string
  icon: LucideIcon
  to: string
  end?: boolean
  shortcut?: string
  /** Carries the "New" mark (07 section 9). */
  isNew?: boolean
}

const mainNav: NavItem[] = [
  { label: "Cases", icon: FolderOpen, to: "/cases", end: true },
  { label: "Triage", icon: ShieldCheck, to: "/triage", end: true },
]

function getLayerAwareCaseNav(caseId: string): NavItem[] {
  return [
    { label: "Graph", icon: Network, to: `/cases/${caseId}/graph`, shortcut: "1" },
    { label: "Timeline", icon: Clock, to: `/cases/${caseId}/timeline`, shortcut: "2" },
    { label: "Map", icon: Map, to: `/cases/${caseId}/map`, shortcut: "3" },
    { label: "Table", icon: TableProperties, to: `/cases/${caseId}/table`, shortcut: "4" },
  ]
}

function getFullDataCaseNav(caseId: string): NavItem[] {
  return [
    { label: "Financial", icon: DollarSign, to: `/cases/${caseId}/financial`, shortcut: "5" },
    { label: "Evidence", icon: FileText, to: `/cases/${caseId}/evidence`, shortcut: "8" },
  ]
}

/** The Phones group (03 D-18): shown only when the case has a phone. */
function getPhonesNav(caseId: string): NavItem[] {
  return [
    { label: "Phone summary", icon: Smartphone, to: `/cases/${caseId}/phones`, end: true },
    { label: "Conversations", icon: MessageSquare, to: `/cases/${caseId}/conversations`, shortcut: "6" },
    { label: "Patterns", icon: Clock, to: `/cases/${caseId}/phone-patterns` },
    { label: "Money on the phones", icon: Banknote, to: `/cases/${caseId}/phone-money` },
    { label: "Analyses", icon: ListChecks, to: `/cases/${caseId}/phone-analyses` },
    { label: "Needs a decision", icon: ShieldCheck, to: `/cases/${caseId}/phone-review` },
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
    { label: "Dossiers", icon: ContactRound, to: `/cases/${caseId}/dossiers` },
    { label: "Reports", icon: ClipboardList, to: `/cases/${caseId}/reports` },
  ]
}

const adminNav: NavItem[] = [
  { label: "AI Costs", icon: DollarSign, to: "/admin/ai-costs" },
  { label: "Updates", icon: CloudDownload, to: "/admin/updates" },
  { label: "Users", icon: Users, to: "/admin/users" },
  { label: "Activity", icon: History, to: "/admin/activity" },
  { label: "Speed", icon: Gauge, to: "/admin/speed" },
  { label: "Profiles", icon: Sliders, to: "/admin/profiles" },
  { label: "Phone registry", icon: Smartphone, to: "/admin/phone-registry" },
]

const settingsItem: NavItem = {
  label: "Settings",
  icon: Settings,
  to: "/settings",
}

function ShortcutHint({ value, active = false }: { value: string; active?: boolean }) {
  return (
    <kbd
      className={cn(
        "ml-auto rounded px-1.5 py-0.5 font-mono text-[10px] font-medium tabular-nums",
        active
          ? "bg-brand-100 text-brand-700 dark:bg-brand-400/15 dark:text-brand-200"
          : "text-sidebar-muted"
      )}
    >
      Ctrl+{value}
    </kbd>
  )
}

function NewMark() {
  return <span className="rounded bg-brand-100 px-1.5 py-0.5 text-[10px] font-semibold text-brand-700 dark:bg-brand-400/15 dark:text-brand-200">New</span>
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
      onPointerEnter={() => preloadRouteIntent(item.to)}
      onFocus={() => preloadRouteIntent(item.to)}
      aria-current={active ? "page" : undefined}
      aria-label={!expanded ? `${item.label}${item.isNew ? ", new" : ""}` : undefined}
      className={cn(
        "group relative flex items-center rounded-lg text-sm font-medium outline-none",
        "transition-[background-color,color,box-shadow,transform] duration-150 ease-[var(--ease-loupe)]",
        "focus-visible:ring-2 focus-visible:ring-ring/35 focus-visible:ring-offset-2 focus-visible:ring-offset-sidebar active:scale-[0.97]",
        expanded ? "h-9 w-full gap-3 px-3" : "mx-auto h-9 w-9 justify-center px-0",
        "text-sidebar-muted hover:bg-slate-50 hover:text-sidebar-foreground dark:hover:bg-white/[0.055]",
        active &&
          (expanded
            ? "bg-brand-50 text-slate-950 shadow-[inset_0_0_0_1px_rgba(180,22,36,0.18)] before:absolute before:left-1.5 before:top-1/2 before:h-5 before:w-0.5 before:-translate-y-1/2 before:rounded-full before:bg-brand-700 dark:bg-brand-400/10 dark:text-slate-50 dark:shadow-[inset_0_0_0_1px_rgba(243,93,109,0.18)] dark:before:bg-brand-400"
            : "bg-slate-900 text-white shadow-[0_10px_20px_-12px_rgba(23,24,28,0.72)] dark:bg-brand-400/15 dark:text-brand-100 dark:shadow-[0_10px_22px_-14px_rgba(0,0,0,0.8)]")
      )}
    >
      <item.icon
        className={cn(
          "size-4 shrink-0 transition-[color,transform] duration-150",
          !expanded && "size-[17px]",
          active && expanded && "text-brand-600 dark:text-brand-300",
          !active && "group-hover:scale-105"
        )}
      />
      {expanded && (
        <span className="min-w-0 flex-1 truncate">{item.label}</span>
      )}
      {expanded && item.isNew && <NewMark />}
      {!expanded && item.isNew && (
        <span className="absolute right-1 top-1 size-1.5 rounded-full bg-brand-600 dark:bg-brand-400" aria-hidden="true" />
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
        <p className="px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.11em] text-sidebar-muted/75">
          {label}
        </p>
      ) : (
        separated && (
          <div
            className="mx-auto mb-2 h-px w-6 bg-sidebar-border"
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
        "group flex min-w-0 items-center overflow-hidden rounded-md outline-none",
        "transition-[box-shadow,transform] duration-150 ease-[var(--ease-loupe)] active:scale-[0.98]",
        "focus-visible:ring-2 focus-visible:ring-ring/35 focus-visible:ring-offset-2 focus-visible:ring-offset-sidebar",
        expanded ? "h-12 w-44" : "mx-auto h-12 w-12"
      )}
    >
      <LoupeLogo
        alt=""
        className="transition-transform duration-200 ease-[var(--ease-loupe)] group-hover:scale-[1.01]"
      />
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
  const { pathname, search } = useLocation()
  // ?phone-prototype=on|off turns the prototype switch on or off for this browser (07 12.1 item D).
  useEffect(() => applySwitchesFromSearch(search), [search])
  const phonePrototype = useSwitch("phone-prototype")
  const { sidebarExpanded: storedSidebarExpanded, toggleSidebar } = useAppStore()
  const narrowViewport = useMediaQuery("(max-width: 767px)")
  const sidebarExpanded = storedSidebarExpanded && !narrowViewport
  const user = useAuthStore((s) => s.user)
  const role = user?.global_role ?? user?.role
  const canSeeAdmin = role === "admin" || role === "super_admin"
  // The phones API module (and its schema library) loads with this query, not with the shell.
  const phones = useQuery({ ...phonesQuery(caseId), enabled: !!caseId, staleTime: 60_000 })
  const hasPhones = (phones.data?.phones.length ?? 0) > 0
  // The "New" mark (07 section 9): its window is worked out here, so after it closes nothing more is asked.
  const client = useQueryClient()
  const [renderedAt] = useState(() => Date.now())
  const markWindow = newMarksUntil(phones.data?.phones.map((p) => p.ingested_at) ?? [])
  const inWindow = hasPhones && renderedAt < markWindow
  const marks = useQuery({ ...marksQuery, enabled: inWindow })
  const showNew = inWindow && !!marks.data && !marks.data.marks.phones_new_hidden
  const hideNew = useMutation({ mutationFn: hideNewMarks, onSuccess: (data) => client.setQueryData(marksQuery.queryKey, data) })

  const toggleButton = (
    <Button
      variant="ghost"
      size={sidebarExpanded ? "default" : "icon"}
      className={cn(
        "mt-1 w-full transition-[background-color,color,box-shadow,transform] active:scale-[0.96]",
        sidebarExpanded
          ? "justify-start text-sidebar-muted hover:bg-slate-50 hover:text-sidebar-foreground dark:hover:bg-white/[0.055]"
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
        "flex h-screen shrink-0 flex-col border-r border-sidebar-border bg-sidebar text-sidebar-foreground shadow-[1px_0_0_rgba(23,24,28,0.03)] dark:shadow-[1px_0_0_rgba(0,0,0,0.24)]",
        "transition-[width] duration-200 ease-[var(--ease-loupe)]",
        sidebarExpanded ? "w-56" : "w-16"
      )}
    >
      <div
        className={cn(
          "flex h-14 items-center border-b border-sidebar-border",
          sidebarExpanded ? "px-4" : "px-2"
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
          <button
            type="button"
            onClick={() => document.dispatchEvent(new CustomEvent("owl:toggle-command-palette"))}
            aria-label={!sidebarExpanded ? "Search this case (Ctrl+K)" : undefined}
            className={cn(
              "mt-3 flex items-center rounded-lg border border-sidebar-border text-sm text-sidebar-muted outline-none hover:bg-slate-50 hover:text-sidebar-foreground focus-visible:ring-2 focus-visible:ring-ring/35 dark:hover:bg-white/[0.055]",
              sidebarExpanded ? "h-9 w-full gap-3 px-3" : "mx-auto h-9 w-9 justify-center px-0",
            )}
          >
            <SearchIcon className="h-4 w-4 shrink-0" aria-hidden />
            {sidebarExpanded && (
              <>
                <span>Search this case</span>
                <kbd className="ml-auto text-[10px]">Ctrl+K</kbd>
              </>
            )}
          </button>
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

        {caseId && (
          <SidebarSection label="Case views" expanded={sidebarExpanded} separated>
            <CaseLayerSwitcher caseId={caseId} expanded={sidebarExpanded} />
            {getLayerAwareCaseNav(caseId).map((item) => (
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
          <SidebarSection label="Full case data" expanded={sidebarExpanded} separated>
            {getFullDataCaseNav(caseId).map((item) => (
              <SidebarLink
                key={item.to}
                item={item}
                expanded={sidebarExpanded}
                active={isItemActive(pathname, item)}
              />
            ))}
            {phonePrototype && (
              <SidebarLink
                item={{ label: "Phones (prototype)", icon: Smartphone, to: `/cases/${caseId}/phones-prototype/summary` }}
                expanded={sidebarExpanded}
                active={pathname.startsWith(`/cases/${caseId}/phones-prototype`)}
              />
            )}
          </SidebarSection>
        )}

        {caseId && hasPhones && (
          <SidebarSection label="Phones" expanded={sidebarExpanded} separated>
            {getPhonesNav(caseId).map((item) => (
              <SidebarLink
                key={item.to}
                item={showNew ? { ...item, isNew: true } : item}
                expanded={sidebarExpanded}
                active={isItemActive(pathname, item) || (item.label === "Conversations" && /\/phones\/[^/]+\/records\/conversations/.test(pathname))}
              />
            ))}
            <SidebarLink
              item={{ label: "Help", icon: CircleHelp, to: `/cases/${caseId}/phones?${HELP_PARAM}=phones` }}
              expanded={sidebarExpanded}
              active={false}
            />
            {showNew && sidebarExpanded && (
              <button
                type="button"
                className="px-3 py-0.5 text-left text-[11px] text-sidebar-muted underline underline-offset-2 hover:text-sidebar-foreground"
                disabled={hideNew.isPending}
                onClick={() => hideNew.mutate()}
              >
                Hide the New marks
              </button>
            )}
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

      <div className="border-t border-sidebar-border p-2">
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
