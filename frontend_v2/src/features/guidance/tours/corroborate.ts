import type { Tour } from "../tours"

/**
 * Corroborate (a panel tour): the selection tray in the corner of every case screen. Behind the switch corroborate-v2;
 * with the switch off the tray is not drawn and this tour never opens.
 */
export const CORROBORATE_TOUR: Tour = {
  area: "corroborate",
  name: "Corroborate",
  // opens once something is selected (the tray's selection panel), not on the three buttons shown on every screen
  panel: '[data-guide="corroborate-tray"][role="region"]',
  steps: [
    { title: "Gather what to check", body: "Press Corroborate beside Add to theory, or right-click a payment, file or event. What you pick gathers here and stays as you move between screens.", targets: ['[data-guide="corroborate-tray"]'] },
    // Only while something is selected.
    { title: "Each part of the selection", body: "Each chip says how many items came from which screen. Click × to take a part out.", targets: ['[data-guide="corroborate-parts"]'] },
    // Only while something is selected.
    { title: "Ask a question of it", body: "Corroborate offers questions about what you selected, each with its count. Pick one to see how strongly the records link it, compared with other times.", targets: ['[data-guide="corroborate-run"]'] },
    { title: "Paste a list", body: "Paste phone numbers, account numbers or plates. Loupe matches each to the case and lists the ones it could not match.", targets: ['[data-guide="corroborate-paste"]'] },
    { title: "Check a claim", body: "Type a sentence someone said. Loupe reads who, when, where and what from it, and checks nothing until you confirm them.", targets: ['[data-guide="corroborate-claim"]'] },
    { title: "Save or combine", body: "Keep a selection under a name and bring it back later, or combine two saved selections.", targets: ['[data-guide="corroborate-saved"]'] },
  ],
}
