import type { Tour } from "../tours"
import { HISTORY } from "./common"

// "keywords-counts" renders once a saved list has run; "keywords-attach" once the case has a saved list.
export const KEYWORDS_TOUR: Tour = {
  area: "keywords",
  name: "Keyword lists",
  steps: [
    { title: "Lists that run on every phone", body: "A keyword list counts its terms on every phone in the case, and again when a phone is added or read. Save one from search with Save as keyword list.", targets: ['[data-guide="keywords-intro"]', "main h1"] },
    { title: "Counts per term and phone", body: "Each row is a term, with a count for each phone. Click a count to see every hit behind it.", targets: ['[data-guide="keywords-counts"]'] },
    { title: "Tie a list to a theory", body: "Attach a list to a theory, and the theory shows the list's current totals.", targets: ['[data-guide="keywords-attach"]'] },
    HISTORY,
  ],
}
