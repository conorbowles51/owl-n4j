import type { Tour } from "../tours"
import { HISTORY } from "./common"

/** The text workbench of one file (/cases/:id/evidence/:fileId/text). */
export const TEXT_TOUR: Tour = {
  area: "text",
  name: "Text workbench",
  steps: [
    { title: "The page as it came in", body: "Original shows the page from the file itself, beside the text read from it.", targets: ['[data-guide="text-original"]'] },
    { title: "The text read from it", body: "Extracted text shows the words read from this page. A Machine reading label means the words were read by machine, so check them against the page.", targets: ['[data-guide="text-extracted"]'] },
    // Not shown while the page's text is missing or the file has no text.
    { title: "Quote a passage", body: "Select words in the text to add them to a finding, a note or a dossier. Each quote keeps a link back to this passage.", targets: ['[data-guide="text-quote"]'] },
    { title: "Find in this document", body: "Type words and press Enter. Each match is marked in the text, and the arrows step from one to the next.", targets: ['[data-guide="text-find"]'] },
    // Only for a file with pages.
    { title: "Turn the pages", body: "Use the arrows, or type a page number and press Enter.", targets: ['[data-guide="text-pages"]'] },
    HISTORY,
  ],
}
