import type { TourStep } from "../tours"

/** Steps and helpers every tour shares. Kept apart from ../tours.ts so the area files can use them. */
export const nav = (route: string) => `nav a[href$="/${route}"]`
export const HISTORY: TourStep = {
  title: "Your steps, one click back",
  body: "Every screen you visit is kept here as a step. Click one to return to exactly that view, or open All steps to search them.",
  targets: ['[data-guide="history-strip"]'],
}
export const GUIDE: TourStep = {
  title: "Help is always here",
  body: "Guide opens this tour again, shows tips you hid, or turns guidance off. Next steps after an action wait here too.",
  targets: ['[data-guide="guide-menu"]'],
}

