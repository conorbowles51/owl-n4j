import type { Tour } from "../tours"
import { HISTORY } from "./common"

/** Phone patterns (/cases/:id/phone-patterns). */
export const PATTERN_TOUR: Tour = {
  area: "pattern",
  name: "Phone patterns",
  steps: [
    { title: "Choose a phone or person", body: "Pick one phone, or a person to see all their phones together. Every view below uses this choice.", targets: ['[data-guide="pattern-subject"]'] },
    { title: "Several ways to look", body: "Day view shows one day hour by hour, and Pattern grid shows four weeks of use. Places over time and Together show where the phones were.", targets: ['[data-guide="pattern-views"]'] },
    { title: "Key dates for the case", body: "Add a key date once and every view offers it. Click one to see the hours around it.", targets: ['[data-guide="pattern-key-dates"]'] },
    { title: "Check what someone said", body: "Type a statement, such as where a person says they were, and see what in the phone supports or undercuts it.", targets: ['[data-guide="pattern-check"]'] },
    // Shows once a view has loaded its result; skipped while it loads or for a case with no phones.
    { title: "Keep a result", body: "Keep this result saves the view as it is now, so it stays the same when the phones are read again.", targets: ['[data-guide="pattern-keep"]'] },
    HISTORY,
  ],
}
