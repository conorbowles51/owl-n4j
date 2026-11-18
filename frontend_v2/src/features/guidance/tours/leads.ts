import type { Tour } from "../tours"
import { HISTORY } from "./common"

export const LEADS_TOUR: Tour = {
  area: "leads",
  name: "Leads",
  steps: [
    { title: "Patterns Loupe found", body: "Each lead is a pattern across the records that may show people acting together, graded against the case's ordinary days. The strongest come first.", targets: ['[data-guide="leads-list"]', "main h1"] },
    { title: "Look again", body: "Look for leads now reads the whole case again. Press it when new material has arrived.", targets: ['[data-guide="leads-find"]'] },
    { title: "One kind at a time", body: "Pick a kind to show only those leads, with the count of each.", targets: ['[data-guide="leads-filters"]'] },
    HISTORY,
  ],
}
