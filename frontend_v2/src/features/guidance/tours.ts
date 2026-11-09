/**
 * First-visit tours (lx-guide C): 3 to 5 popups per area, each pointing at a real control. A step names its target by
 * a list of candidates, tried in order: a CSS selector, or `text=<words>` for a button or link with those words. A
 * step whose control is not on screen (a panel closed, an empty case) is shown in the middle of the screen, never
 * skipped silently and never pointed at the wrong thing.
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
}

export type TourArea =
  | "workspace" | "evidence" | "graph" | "timeline" | "map" | "financial" | "phones" | "agent"

const nav = (route: string) => `nav a[href$="/${route}"]`
const HISTORY: TourStep = {
  title: "Your steps, one click back",
  body: "Every screen you visit is kept here as a step. Click one to return to exactly that view, or open All steps to search them.",
  targets: ['[data-guide="history-strip"]'],
}
const GUIDE: TourStep = {
  title: "Help is always here",
  body: "Guide opens this tour again, shows tips you hid, or turns guidance off. Next steps after an action wait here too.",
  targets: ['[data-guide="guide-menu"]'],
}

export const TOURS: Record<TourArea, Tour> = {
  workspace: {
    area: "workspace",
    name: "Case home",
    steps: [
      { title: "This is the case home", body: "Theories, findings, notes and tasks for the case live here. Start here steps show what to do first.", targets: ['[data-guide="start-here"]', "main h1", "main"] },
      { title: "Every view of the case", body: "The side menu opens the evidence, the graph, the timeline, the map, the money and the phones.", targets: [nav("evidence"), "nav"] },
      { title: "Search the whole case", body: "Press Ctrl+K to search every document, payment, message and name in the case.", targets: ['[data-guide="case-search"]', nav("search")] },
      HISTORY,
      GUIDE,
    ],
  },
  evidence: {
    area: "evidence",
    name: "Evidence",
    steps: [
      { title: "Your files, as they came in", body: "Upload documents, statements, phone reports and recordings here. Folders keep the production's order.", targets: ['[data-guide="evidence-upload"]', "text=Upload", "main"] },
      { title: "Process a file to read it", body: "Processing finds the names, dates, places and payments in a file. Next steps appear when it finishes.", targets: ["text=Process", "main"] },
      { title: "Work in progress", body: "The Jobs list shows what is being read and how long it has left. You can keep working meanwhile.", targets: ['[data-guide="jobs-panel"]', '[data-panel-id="case-side-panel"]'] },
      HISTORY,
    ],
  },
  graph: {
    area: "graph",
    name: "Graph",
    steps: [
      { title: "Who is linked to whom", body: "Each dot is a person, company, account or place found in the evidence; each line is a link between them.", targets: ["canvas", "main"] },
      { title: "Zoom and focus", body: "Zoom in, then click a dot to see where it comes from. Right-click it to expand its links or merge duplicates.", targets: ['[aria-label="Zoom in"]'] },
      { title: "Keep what matters", body: "Select dots and add them to a theory, so the reason you chose them stays with them.", targets: ["text=Add to theory", "main"] },
      HISTORY,
    ],
  },
  timeline: {
    area: "timeline",
    name: "Timeline",
    steps: [
      { title: "Everything in date order", body: "Events, payments, messages and documents from the case, one line per day.", targets: ["main"] },
      { title: "Choose what to show", body: "Switch the view or narrow the dates to the period you are looking at.", targets: ['[aria-label="View"]', "main"] },
      { title: "Events with no time", body: "Things with a date but no time sit apart, so the order you read is never guessed.", targets: ['[aria-label="Events with no time recorded"]', "main"] },
      HISTORY,
    ],
  },
  map: {
    area: "map",
    name: "Map",
    steps: [
      { title: "Where things happened", body: "Addresses from the evidence and phone positions, on one map.", targets: ['[aria-label="Places map"]', "main"] },
      { title: "Draw an area", body: "Draw around a place to see what happened there and add it to a theory.", targets: ["text=Draw", "main"] },
      HISTORY,
    ],
  },
  financial: {
    area: "financial",
    name: "Financial",
    steps: [
      { title: "The money in the case", body: "Overview gives the totals; NEXT FOR YOU lists the work that is waiting.", targets: ["text=Overview", "main"] },
      { title: "Every payment", body: "Transactions lists each payment with its statement line. Filter by account, month or name.", targets: ["text=Transactions", "main"] },
      { title: "Follow the money", body: "See where money went, account to account, with each step cited to its statement.", targets: ["text=Follow the money", "main"] },
      { title: "Statements to check", body: "Lines that could not be read with certainty wait under Statements for a person to check.", targets: ["text=Statements", "main"] },
      HISTORY,
    ],
  },
  phones: {
    area: "phones",
    name: "Phones",
    steps: [
      { title: "Each phone in the case", body: "Open a phone to see who it belongs to, who they talk to most and what it holds.", targets: ["main"] },
      { title: "Messages and calls", body: "Conversations, calls, media and locations each have their own screen in the side menu.", targets: [nav("phones"), "nav"] },
      { title: "Analyses across phones", body: "Compare phones, find shared contacts and see deletions over time.", targets: [nav("phone-analyses"), "nav"] },
      HISTORY,
    ],
  },
  agent: {
    area: "agent",
    name: "Agent",
    steps: [
      { title: "Ask about the case", body: "Ask a question in your own words. The agent answers from the case's evidence and cites each source.", targets: ['[aria-label="Send agent prompt"]', "textarea"] },
      { title: "Guided workflows", body: "Pick a ready-made line of enquiry, such as tracing a payment or building a timeline for a person.", targets: ['[aria-label="Guided workflows"]', "main"] },
      { title: "A fresh start", body: "Start a new thread for a new question, so each answer keeps its own sources.", targets: ['[aria-label="New agent thread"]', "main"] },
      HISTORY,
    ],
  },
}

/** The tour for a case address, or null for a screen without one. */
export function tourArea(pathname: string): TourArea | null {
  const m = /^\/cases\/[^/]+\/?([^/?#]*)/.exec(pathname)
  if (!m) return null
  const first = m[1] || "workspace"
  if (first === "phones" || first.startsWith("phone-") || first === "conversations") return "phones"
  return (first in TOURS ? first : null) as TourArea | null
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
