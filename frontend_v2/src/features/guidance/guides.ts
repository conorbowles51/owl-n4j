import type { GuideSource } from "@/components/ui/guide-dialog"
import { GLOSSARY_GUIDE } from "@/components/ui/glossary"
import type { TourArea } from "./tours"

/**
 * The guide for each area (lx-guidecover F), opened from Guide in the case's bottom bar. Every area has one; some
 * share a guide (the document reader is in the Evidence guide). The financial and phone guides are the ones those
 * screens have always had.
 */
const base = import.meta.env.BASE_URL
const g = (id: string, title: string): GuideSource => ({
  id,
  label: title,
  title,
  url: `${base}docs/guides/${id}.md`,
  directory: `${base}docs/guides/`,
  heading: `# ${title}`,
  prefix: `guide-${id}`,
})

export const GUIDES = {
  "case-home": g("case-home", "Case home guide"),
  evidence: g("evidence", "Evidence guide"),
  graph: g("graph", "Graph guide"),
  timeline: g("timeline", "Timeline guide"),
  map: g("map", "Map guide"),
  assistant: g("assistant", "Case assistant guide"),
  search: g("search", "Search guide"),
  corroborate: g("corroborate", "Corroborate guide"),
  theories: g("theories", "Theories guide"),
  dossiers: g("dossiers", "Dossiers guide"),
  financial: {
    id: "financial",
    label: "Financial user guide",
    title: "Financial user guide",
    url: `${base}docs/financial-guide/financial-user-guide.md`,
    directory: `${base}docs/financial-guide/`,
    heading: "# Loupe financial user guide",
    prefix: "financial-guide",
  },
  phones: {
    id: "phones",
    label: "Phone user guide",
    title: "Phone user guide",
    url: `${base}docs/phone-guide/phone-user-guide.md`,
    directory: `${base}docs/phone-guide/`,
    heading: "# Phone user guide",
    prefix: "phone-guide",
  },
} satisfies Record<string, GuideSource>

export type GuideId = keyof typeof GUIDES

/** Which guide each tour area opens. */
export const AREA_GUIDE: Record<TourArea, GuideId> = {
  workspace: "case-home",
  reports: "case-home",
  settings: "case-home",
  evidence: "evidence",
  text: "evidence",
  graph: "graph",
  table: "graph",
  timeline: "timeline",
  map: "map",
  agent: "assistant",
  chat: "assistant",
  search: "search",
  keywords: "search",
  corroborate: "corroborate",
  relations: "corroborate",
  leads: "corroborate",
  corropanel: "corroborate",
  theory: "theories",
  dossiers: "dossiers",
  financial: "financial",
  phones: "phones",
  conversations: "phones",
  analyses: "phones",
  pattern: "phones",
}

/** The area's guide first, then the glossary, for the Guide dialog's chooser. */
export function guidesFor(area: TourArea): GuideSource[] {
  return [GUIDES[AREA_GUIDE[area]], GLOSSARY_GUIDE]
}
