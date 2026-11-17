import type { Tour } from "../tours"
import { HISTORY } from "./common"

/**
 * Phone analyses: the index (/cases/:id/phone-analyses), each analysis under it and Money on the phones
 * (/cases/:id/phone-money) share this tour. Steps not on the screen first visited are skipped.
 */
export const ANALYSES_TOUR: Tour = {
  area: "analyses",
  name: "Phone analyses",
  steps: [
    // Index page only.
    { title: "Analyses across the phones", body: "Each analysis looks across the case's phones for one kind of lead. Open one to see what it does and run it.", targets: ['[data-guide="analyses-list"]'] },
    // Index page only, and only once a result has been kept.
    { title: "Results you kept", body: "Kept results open in their analysis as they were kept. Export the records behind each one from here.", targets: ['[data-guide="analyses-kept"]'] },
    // An analysis page only (not the index).
    { title: "Run the analysis", body: "Run checks the case's phones for this analysis. Each result is a lead to examine, not a finding.", targets: ['[data-guide="analyses-run"]'] },
    HISTORY,
  ],
}
