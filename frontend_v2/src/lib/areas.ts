/**
 * Area identity (lx-style B and C). Every case view belongs to one area family; the area gives the view its hue
 * (globals.css `--area-<id>`, `-soft`, `-foreground`), shown on the case navigation icon and active mark, the view
 * header band and rule, the page title icon and empty states. One list, read by the sidebar, the view header and
 * the tests, so no view hand-rolls its own colour. Brand red stays the action and active colour.
 */
import {
  Bot,
  Briefcase,
  ClipboardList,
  Clock,
  ContactRound,
  DollarSign,
  FileText,
  Map,
  MessageSquare,
  Network,
  Settings,
  Smartphone,
  TableProperties,
  type LucideIcon,
} from "lucide-react"

export const AREA_IDS = [
  "investigate",
  "money",
  "phones",
  "people",
  "evidence",
  "assistant",
  "work",
  "settings",
] as const
export type AreaId = (typeof AREA_IDS)[number]

/** The area's name as shown in the view header, and the brand palette hue it is drawn from. */
export const AREAS: Record<AreaId, { label: string; from: string }> = {
  investigate: { label: "Investigate", from: "location (node palette)" },
  money: { label: "Money", from: "financial (node palette)" },
  phones: { label: "Phones", from: "communication (node palette)" },
  people: { label: "People", from: "person (node palette)" },
  evidence: { label: "Evidence", from: "vehicle (node palette)" },
  assistant: { label: "Assistant", from: "organisation (node palette)" },
  work: { label: "Work", from: "event (node palette)" },
  settings: { label: "Case", from: "neutral (charcoal)" },
}

export interface CaseView {
  /** The first path segment below /cases/:id. */
  segment: string
  title: string
  area: AreaId
  icon: LucideIcon
}

/** Every case view on the case shell, in navigation order. `profiles` redirects to `dossiers`. */
export const CASE_VIEWS: CaseView[] = [
  { segment: "graph", title: "Graph", area: "investigate", icon: Network },
  { segment: "timeline", title: "Timeline", area: "investigate", icon: Clock },
  { segment: "map", title: "Map", area: "investigate", icon: Map },
  { segment: "table", title: "Table", area: "investigate", icon: TableProperties },
  { segment: "financial", title: "Financial", area: "money", icon: DollarSign },
  { segment: "cellebrite", title: "Phones", area: "phones", icon: Smartphone },
  { segment: "phones-prototype", title: "Phones (prototype)", area: "phones", icon: Smartphone },
  { segment: "dossiers", title: "Dossiers", area: "people", icon: ContactRound },
  { segment: "profiles", title: "Dossiers", area: "people", icon: ContactRound },
  { segment: "evidence", title: "Evidence", area: "evidence", icon: FileText },
  { segment: "chat", title: "Chat", area: "assistant", icon: MessageSquare },
  { segment: "agent", title: "Agent", area: "assistant", icon: Bot },
  { segment: "workspace", title: "Workspace", area: "work", icon: Briefcase },
  { segment: "reports", title: "Reports", area: "work", icon: ClipboardList },
  { segment: "settings", title: "Case settings", area: "settings", icon: Settings },
]

/** The case view for a pathname such as /cases/<id>/financial?x, or undefined outside a case view. */
export function caseViewFor(pathname: string): CaseView | undefined {
  const m = pathname.match(/^\/cases\/[^/]+\/([^/?#]+)/)
  if (!m) return undefined
  return CASE_VIEWS.find((v) => v.segment === m[1])
}

/**
 * Tailwind classes per area, written out in full so Tailwind's scanner sees every class (a class built from a
 * template string is never generated). One place for every area-coloured surface.
 */
export const AREA_CLASSES: Record<
  AreaId,
  { text: string; fg: string; soft: string; bg: string; border: string; before: string; ring: string }
> = {
  investigate: {
    text: "text-area-investigate",
    fg: "text-area-investigate-foreground",
    soft: "bg-area-investigate-soft",
    bg: "bg-area-investigate",
    border: "border-area-investigate",
    before: "before:bg-area-investigate",
    ring: "shadow-[inset_0_0_0_1px_hsl(var(--area-investigate)/0.35)]",
  },
  money: {
    text: "text-area-money",
    fg: "text-area-money-foreground",
    soft: "bg-area-money-soft",
    bg: "bg-area-money",
    border: "border-area-money",
    before: "before:bg-area-money",
    ring: "shadow-[inset_0_0_0_1px_hsl(var(--area-money)/0.35)]",
  },
  phones: {
    text: "text-area-phones",
    fg: "text-area-phones-foreground",
    soft: "bg-area-phones-soft",
    bg: "bg-area-phones",
    border: "border-area-phones",
    before: "before:bg-area-phones",
    ring: "shadow-[inset_0_0_0_1px_hsl(var(--area-phones)/0.35)]",
  },
  people: {
    text: "text-area-people",
    fg: "text-area-people-foreground",
    soft: "bg-area-people-soft",
    bg: "bg-area-people",
    border: "border-area-people",
    before: "before:bg-area-people",
    ring: "shadow-[inset_0_0_0_1px_hsl(var(--area-people)/0.35)]",
  },
  evidence: {
    text: "text-area-evidence",
    fg: "text-area-evidence-foreground",
    soft: "bg-area-evidence-soft",
    bg: "bg-area-evidence",
    border: "border-area-evidence",
    before: "before:bg-area-evidence",
    ring: "shadow-[inset_0_0_0_1px_hsl(var(--area-evidence)/0.35)]",
  },
  assistant: {
    text: "text-area-assistant",
    fg: "text-area-assistant-foreground",
    soft: "bg-area-assistant-soft",
    bg: "bg-area-assistant",
    border: "border-area-assistant",
    before: "before:bg-area-assistant",
    ring: "shadow-[inset_0_0_0_1px_hsl(var(--area-assistant)/0.35)]",
  },
  work: {
    text: "text-area-work",
    fg: "text-area-work-foreground",
    soft: "bg-area-work-soft",
    bg: "bg-area-work",
    border: "border-area-work",
    before: "before:bg-area-work",
    ring: "shadow-[inset_0_0_0_1px_hsl(var(--area-work)/0.35)]",
  },
  settings: {
    text: "text-area-settings",
    fg: "text-area-settings-foreground",
    soft: "bg-area-settings-soft",
    bg: "bg-area-settings",
    border: "border-area-settings",
    before: "before:bg-area-settings",
    ring: "shadow-[inset_0_0_0_1px_hsl(var(--area-settings)/0.35)]",
  },
}
