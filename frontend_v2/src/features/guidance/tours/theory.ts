import type { Tour } from "../tours"

/** An open theory (a panel tour): the casework detail of a theory, while it is read rather than edited. */
export const THEORY_TOUR: Tour = {
  area: "theory",
  name: "Theory",
  panel: '[data-guide="theory-panel"]',
  steps: [
    { title: "This is a theory", body: "A theory holds what you think happened and the items that bear on it. Edit changes its text; every version is kept under Revision history.", targets: ['[data-guide="theory-panel"]'] },
    // Only once something is linked to the theory.
    { title: "What bears on it", body: "Each linked item says whether it supports, contradicts or is context. Changed since cited marks a payment that changed after it was added.", targets: ['[data-guide="theory-links"]'] },
    // Only once something is linked to the theory.
    { title: "For and against", body: "Open this to see what supports the theory beside what contradicts it.", targets: ['[data-guide="theory-compare"]'] },
    // Only while some links were added without saying how they bear on it.
    { title: "Links to review", body: "These were added without saying how they bear on the theory. Choose Supports, Contradicts or Context for each.", targets: ['[data-guide="theory-review"]'] },
    { title: "Read it as a whole", body: "Reading & analysis shows every addition with why it was chosen, other explanations and what breaks the theory. Where a line offers Corroborate this claim, it checks that line against the phones.", targets: ['[data-guide="theory-reading"]'] },
    // Only for someone who can edit, and not once the theory has been converted.
    { title: "When it holds up", body: "Convert to finding turns the theory into a finding and carries its narratives with it.", targets: ['[data-guide="theory-convert"]'] },
  ],
}
