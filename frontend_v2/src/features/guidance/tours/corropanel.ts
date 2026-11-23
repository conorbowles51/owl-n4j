import type { Tour } from "../tours"

/** Corroborate from anywhere (a panel tour): the Corroborate panel over the page. Behind the switch corroborate-v2. */
export const CORROPANEL_TOUR: Tour = {
  area: "corropanel",
  name: "Corroborate panel",
  panel: '[data-guide="corroborate-panel"]',
  steps: [
    { title: "Corroborate what you chose", body: "This panel asks about the person, phone, line or photo you chose, without leaving the page.", targets: ['[data-guide="corroborate-panel"]'] },
    { title: "Leads already here", body: "The leads that touch these records, people or dates. Open one to read what raises and lowers it.", targets: ['[data-guide="corroborate-panel-here"]'] },
    { title: "Ask a new question", body: "Pick a question that fits what you chose. The answer is saved to Leads as Asked by you, a reading by Loupe until you confirm it.", targets: ['[data-guide="corroborate-panel-ask"]'] },
  ],
}
