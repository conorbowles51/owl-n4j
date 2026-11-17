import { GUIDE, HISTORY, nav } from "./tours/common"
import { MORE_TOURS, type MoreArea } from "./tours/index"

/**
 * First-visit tours (lx-guide C, lx-guidecover D): 3 to 6 popups per area, each pointing at a real control. A step
 * names its target by a list of candidates, tried in order: a CSS selector, or `text=<words>` for a button or link
 * with those words. A step whose control is not on screen (a panel closed, an empty case, a feature switched off) is
 * skipped, never pointed at nothing; "main" names the whole screen, for a step about the screen itself. A tour with
 * no step on screen does not open.
 *
 * A route tour belongs to a case address (tourArea); a panel tour (`panel`) belongs to a panel that opens on many
 * screens, such as Corroborate, and opens the first time that panel is on screen.
 */
export interface TourStep {
  title: string
  body: string
  targets: string[]
}

export interface Tour {
  area: TourArea
  name: string
  steps: TourStep[]
  /** A panel tour: the selector of the open panel. */
  panel?: string
}

export type TourArea =
  | "workspace" | "evidence" | "graph" | "timeline" | "map" | "financial" | "phones" | "agent" | MoreArea


export const TOURS: Record<TourArea, Tour> = {
  ...MORE_TOURS,
  workspace: {
    area: "workspace",
    name: "Case home",
    steps: [
      { title: "This is the case home", body: "Theories, findings, notes and tasks for the case live here. Start here steps show what to do first.", targets: ['[data-guide="start-here"]', "main h1"] },
      { title: "Every view of the case", body: "The side menu opens the evidence, the graph, the timeline, the map, the money and the phones.", targets: [nav("evidence")] },
      { title: "Search the whole case", body: "Press Ctrl+K to search every document, payment, message and name in the case. Results found by meaning come graded, each with why it matched.", targets: ['[data-guide="case-search"]', nav("search")] },
      HISTORY,
      GUIDE,
    ],
  },
  evidence: {
    area: "evidence",
    name: "Evidence",
    steps: [
      { title: "Your files, as they came in", body: "Upload documents, statements, phone reports and recordings here. Folders keep the production's order.", targets: ['[data-guide="evidence-upload"]', "text=Upload"] },
      { title: "Process a file to read it", body: "Processing finds the names, dates, places and payments in a file. Next steps appear when it finishes.", targets: ["text=Process"] },
      { title: "Work in progress", body: "The Jobs list shows what is being read and how long it has left. A phone report has its own card with the stage in words and the counts so far. You can keep working meanwhile.", targets: ['[data-guide="jobs-panel"]', '[data-panel-id="case-side-panel"]'] },
      { title: "Nothing deleted is lost", body: "Deleted files and folders wait in Deleted items for 30 days. Restore them from there, or delete them for good.", targets: ['[data-guide="evidence-deleted"]'] },
      { title: "Photos, videos and missing files", body: "A photo's date, place and camera come from its own data and are marked as not checked. Videos are read in full, frames and a transcript. A file marked File missing is restored by uploading it again.", targets: ['[data-guide="evidence-upload"]', "text=Upload"] },
      HISTORY,
    ],
  },
  graph: {
    area: "graph",
    name: "Graph",
    steps: [
      { title: "Who is linked to whom", body: "Each dot is a person, company, account or place found in the evidence; each line is a link between them.", targets: ["canvas"] },
      { title: "Zoom and focus", body: "Zoom in, then click a dot to see where it comes from. Right-click it to expand its links or merge duplicates.", targets: ['[aria-label="Zoom in"]'] },
      { title: "Keep what matters", body: "Select dots and add them to a theory, so the reason you chose them stays with them.", targets: ["text=Add to theory"] },
      { title: "People in contact", body: "Pairs of people who messaged, called or emailed each other on the phones. Open the list to see each pair and their messages.", targets: ['[data-guide="graph-people-in-contact"]'] },
      HISTORY,
    ],
  },
  timeline: {
    area: "timeline",
    name: "Timeline",
    steps: [
      { title: "Everything in date order", body: "Events, payments, messages and documents from the case, one line per day.", targets: ["main"] },
      { title: "Choose what to show", body: "Switch the view or narrow the dates to the period you are looking at.", targets: ['[aria-label="View"]'] },
      { title: "Events with no time", body: "Things with a date but no time sit apart, so the order you read is never guessed.", targets: ['[aria-label="Events with no time recorded"]'] },
      { title: "Photos with a date", body: "A dated photo shows as Photo taken, with a thumbnail. Its date comes from the photo's own data and has not been checked by a person.", targets: ["main"] },
      HISTORY,
    ],
  },
  map: {
    area: "map",
    name: "Map",
    steps: [
      { title: "Where things happened", body: "Addresses from the evidence and phone positions, on one map.", targets: ['[aria-label="Places map"]'] },
      { title: "Draw an area", body: "Areas, then Draw area: draw around a place to see what happened there and add it to a theory.", targets: ['[data-guide="map-areas"]'] },
      { title: "Photos on the map", body: "A photo whose data holds a place shows as a pin. The place comes from the photo's own data and has not been checked by a person.", targets: ['[aria-label="Places map"]'] },
      { title: "Each phone's route", body: "Show routes draws each phone's path in time order. Gaps of more than 2 hours are left out and counted.", targets: ['[data-guide="map-routes"]'] },
      HISTORY,
    ],
  },
  financial: {
    area: "financial",
    name: "Financial",
    steps: [
      { title: "The money in the case", body: "Overview gives the totals; NEXT FOR YOU lists the work that is waiting.", targets: ["text=Overview"] },
      { title: "Every payment", body: "Transactions lists each payment with its statement line. Filter by account, month or name.", targets: ["text=Transactions"] },
      { title: "Follow the money", body: "See where money went, account to account, with each step cited to its statement.", targets: ["text=Follow the money"] },
      { title: "Statements to check", body: "Lines that could not be read with certainty, and possible copies of a statement already imported, wait under Statements for a person to decide.", targets: ["text=Statements"] },
      { title: "Calls the reader made", body: "Where a statement does not print a value outright, the reader's choice is listed here. Mark it Looks right, or correct it before import.", targets: ['[data-guide="financial-judgement-calls"]'] },
      { title: "Two statements side by side", body: "Compare side by side shows a possible copy next to its original, with the facts that agree and differ.", targets: ['[data-guide="financial-compare"]'] },
    ],
  },
  phones: {
    area: "phones",
    name: "Phones",
    steps: [
      { title: "Each phone in the case", body: "Open a phone to see who it belongs to, who they talk to most and what it holds.", targets: ["main"] },
      { title: "Choose the phones", body: "Turn each phone on or off. A phone that is off is not drawn or counted on any phone screen.", targets: ['[data-guide="phone-layers"]'] },
      { title: "Messages and calls", body: "Conversations, calls, media and locations each have their own screen in the side menu.", targets: [nav("phones")] },
      { title: "Analyses across phones", body: "Compare phones, find shared contacts and see deletions over time.", targets: [nav("phone-analyses")] },
      { title: "Check the report itself", body: "Read again reads a phone a second time with an independent tool and lists where it differs from the report. A record's panel shows the database row it came from.", targets: [nav("phone-analyses")] },
      HISTORY,
    ],
  },
  agent: {
    area: "agent",
    name: "Agent",
    steps: [
      { title: "Ask about the case", body: "Ask a question in your own words. The agent answers from the case's evidence and cites each source. A Source check at the end says which citations support what they are cited for.", targets: ['[aria-label="Send agent prompt"]', "textarea"] },
      { title: "Go deeper", body: "Deep investigation reads the whole case, works through a checklist and writes a full report. It takes longer and costs more; the switch says how much.", targets: ['[data-guide="agent-deep"]'] },
      { title: "Steer the tools", body: "While the assistant works, a line names each step and the time so far. Choose which kinds of record it may search. Groups you switch off are listed as not examined in the answer.", targets: ['[data-guide="agent-tools"]'] },
      { title: "Guided workflows", body: "Pick a ready-made line of enquiry, such as tracing a payment or building a timeline for a person.", targets: ['[aria-label="Guided workflows"]'] },
      { title: "Rate an answer", body: "Say an answer missed something, was not relevant or was too thin. Your rating is kept with the answer.", targets: ['[data-guide="agent-rate"]'] },
      HISTORY,
    ],
  },
}

/** The tour for a case address, or null for a screen without one. */
export function tourArea(pathname: string): TourArea | null {
  const m = /^\/cases\/[^/]+\/?([^?#]*)/.exec(pathname)
  if (!m) return null
  const parts = m[1].split("/").filter(Boolean)
  const first = parts[0] || "workspace"
  if (first === "conversations" || (first === "phones" && parts[2] === "records" && parts[3] === "conversations")) return "conversations"
  if (first === "phone-analyses" || first === "phone-money") return "analyses"
  if (first === "phone-patterns") return "pattern"
  if (first === "keyword-lists") return "keywords"
  if (first === "evidence" && parts[2] === "text") return "text"
  if (first === "phones" || first.startsWith("phone") || first === "records") return "phones"
  const area = first in TOURS && !TOURS[first as TourArea].panel ? (first as TourArea) : null
  return area
}

/** The panel tours whose panel is on screen now, first opened first in the list. */
export function panelAreas(root: ParentNode = document): TourArea[] {
  return (Object.values(TOURS) as Tour[]).filter((t) => t.panel && findTarget([t.panel], root)).map((t) => t.area)
}

/** The steps of a tour whose control is on screen, in order; "main" (the screen itself) always counts. */
export function stepsOnScreen(tour: Tour, root: ParentNode = document): TourStep[] {
  return tour.steps.filter((s) => s.targets.some((t) => t === "main" || findTarget([t], root)))
}

/** The first candidate on screen and visible. */
export function findTarget(targets: string[], root: ParentNode = document): HTMLElement | null {
  for (const t of targets) {
    let el: HTMLElement | null = null
    if (t.startsWith("text=")) {
      const words = t.slice(5).toLowerCase()
      el =
        Array.from(root.querySelectorAll<HTMLElement>("button, a, [role='tab']")).find(
          (b) => (b.textContent ?? "").trim().toLowerCase().startsWith(words) && visible(b)
        ) ?? null
    } else {
      try {
        el = Array.from(root.querySelectorAll<HTMLElement>(t)).find(visible) ?? null
      } catch {
        el = null
      }
    }
    if (el) return el
  }
  return null
}

function visible(el: HTMLElement): boolean {
  const r = el.getBoundingClientRect()
  return r.width > 0 && r.height > 0
}
