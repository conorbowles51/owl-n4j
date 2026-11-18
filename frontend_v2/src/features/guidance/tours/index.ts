import type { Tour } from "../tours"
import { ANALYSES_TOUR } from "./analyses"
import { CHAT_TOUR } from "./chat"
import { CONVERSATIONS_TOUR } from "./conversations"
import { CORROBORATE_TOUR } from "./corroborate"
import { DOSSIERS_TOUR } from "./dossiers"
import { KEYWORDS_TOUR } from "./keywords"
import { LEADS_TOUR } from "./leads"
import { PATTERN_TOUR } from "./pattern"
import { RELATIONS_TOUR } from "./relations"
import { REPORTS_TOUR } from "./reports"
import { SEARCH_TOUR } from "./search"
import { SETTINGS_TOUR } from "./settings"
import { TABLE_TOUR } from "./table"
import { TEXT_TOUR } from "./text"
import { THEORY_TOUR } from "./theory"

/**
 * The tours added by lx-guidecover, one file per area. Route areas follow tourArea() in ../tours.ts; panel tours
 * (Corroborate, a theory) carry `panel`, the selector of their open panel.
 */
export type MoreArea =
  | "analyses" | "chat" | "conversations" | "corroborate" | "dossiers" | "keywords" | "leads" | "pattern" | "relations"
  | "reports" | "search" | "settings" | "table" | "text" | "theory"

export const MORE_TOURS: Record<MoreArea, Tour> = {
  analyses: ANALYSES_TOUR,
  chat: CHAT_TOUR,
  conversations: CONVERSATIONS_TOUR,
  corroborate: CORROBORATE_TOUR,
  dossiers: DOSSIERS_TOUR,
  keywords: KEYWORDS_TOUR,
  leads: LEADS_TOUR,
  pattern: PATTERN_TOUR,
  relations: RELATIONS_TOUR,
  reports: REPORTS_TOUR,
  search: SEARCH_TOUR,
  settings: SETTINGS_TOUR,
  table: TABLE_TOUR,
  text: TEXT_TOUR,
  theory: THEORY_TOUR,
}
