import type { Tour } from "../tours"
import { HISTORY } from "./common"

export const LEADS_TOUR: Tour = {
  area: "leads",
  name: "Leads",
  steps: [
    { title: "Patterns Loupe found", body: "Each lead is a pattern across the records that may show people acting together, graded against the case's ordinary days. The strongest come first.", targets: ['[data-guide="leads-list"]', "main h1"] },
    { title: "Look again", body: "Look for leads now reads the whole case again. On a case it can read in up to 20 minutes, Loupe also looks again by itself when new material arrives; otherwise the page says new material has arrived.", targets: ['[data-guide="leads-find"]'] },
    { title: "One kind at a time", body: "Pick a kind to show only those leads, with the count of each.", targets: ['[data-guide="leads-filters"]'] },
    { title: "See a lead's records", body: "Show these records marks the lead's records on Conversations, the Timeline and the Map, with a bar that opens the lead's days.", targets: ['[data-guide="lead-show-records"]'] },
    HISTORY,
  ],
}
