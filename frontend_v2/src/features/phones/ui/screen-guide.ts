/** Which part of the phone guide each case screen opens at (07 section 9): the heading in phone-user-guide.md. */
const SCREEN_GUIDE: Record<string, string> = {
  phones: "first-look-at-a-phone",
  conversations: "read-a-conversation-around-a-date",
  "phone-patterns": "where-was-the-phone-and-were-two-people-together",
  "phone-money": "explain-a-finding",
  "phone-analyses": "find-deleted-or-concealed-material",
  "phone-review": "check-the-systems-readings",
  map: "where-was-the-phone-and-were-two-people-together",
  timeline: "the-window-around-a-moment-across-phones",
  graph: "everything-with-one-person-or-between-two",
  search: "search-everything-and-read-the-hit-in-context",
  evidence: "add-a-phone-and-know-it-arrived-whole",
  dossiers: "build-the-case-while-reading",
  workspace: "build-the-case-while-reading",
}

export const GUIDE_SCREENS = Object.values(SCREEN_GUIDE)

/** The guide heading for a case address; screens without one open the guide at its start. */
export function guideAnchor(pathname: string): string | undefined {
  const screen = pathname.match(/^\/cases\/[^/]+\/([^/?#]+)/)?.[1]
  return screen ? SCREEN_GUIDE[screen] : undefined
}
