import type { Tour } from "../tours"
import { HISTORY } from "./common"

// "search-add" and "search-hits" render only when the search has at least one hit.
export const SEARCH_TOUR: Tour = {
  area: "search",
  name: "Search results",
  steps: [
    { title: "Every match, not a sample", body: "This page lists every hit of one kind for your search, read in full. The count says how many matched.", targets: ['[data-guide="search-heading"]', "main"] },
    { title: "Open or choose hits", body: "Click a hit to open it where it was found. Tick the hits you want to keep, or tick Every hit.", targets: ['[data-guide="search-hits"]'] },
    { title: "Keep what you chose", body: "Add the chosen hits to a dossier, theory, note, timeline or label, or corroborate them.", targets: ['[data-guide="search-add"]'] },
    HISTORY,
  ],
}
