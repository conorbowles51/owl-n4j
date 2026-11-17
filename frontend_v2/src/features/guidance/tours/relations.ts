import type { Tour } from "../tours"
import { HISTORY } from "./common"

// Every step after the first renders only once the analysis has finished with a link result (not while it is
// working, after it stopped, or for a single-claim check); absent steps are skipped.
export const RELATIONS_TOUR: Tour = {
  area: "relations",
  name: "Corroborate",
  steps: [
    { title: "Items you marked as related", body: "This page checks the items you chose against the records. It shows what occurs together, never why.", targets: ['[data-guide="relations-header"]', "main h1"] },
    { title: "Ask, export or run again", body: "Ask the agent how the items could be linked, export the report as a PDF, or run the analysis again.", targets: ['[data-guide="relations-actions"]'] },
    { title: "Candidate links", body: "Each link found says why, with its strength. The strongest come first, and weak links are labelled weak.", targets: ['[data-guide="relations-candidates"]'] },
    { title: "Where no link was found", body: "Each pair says what was searched. No link found is not proof that none exists.", targets: ['[data-guide="relations-no-links"]'] },
    { title: "Explanations to weigh", body: "Drafted explanations are model readings, each with the records for and against. Accept one into a theory as supports or contradicts.", targets: ['[data-guide="relations-explanations"]'] },
    HISTORY,
  ],
}
