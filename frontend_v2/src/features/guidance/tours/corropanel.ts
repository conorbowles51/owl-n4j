import type { Tour } from "../tours"

/**
 * The Corroborate page (/cases/:id/corroborate). Pressing Corroborate on any screen opens it with the question filled
 * from what was chosen. The area keeps its old key so saved tour progress and the feature list still match.
 */
export const CORROPANEL_TOUR: Tour = {
  area: "corropanel",
  name: "Corroborate page",
  steps: [
    { title: "Your question", body: "The question is a sentence built from what you chose. Click a blue part to change the people, the relation or the days.", targets: ['[data-guide="corroborate-question"]', "main h1"] },
    { title: "Ask", body: "Nothing runs until you press Ask. Loupe compares the days that matter with ordinary days, using fixed rules, never AI.", targets: ['[data-guide="corroborate-ask"]'] },
    { title: "Leads already here", body: "Leads Loupe found lists the patterns it found by itself. Your earlier questions keeps every answer you asked for, a reading by Loupe until you confirm it.", targets: ['[data-guide="corroborate-tabs"]'] },
  ],
}
