import type { Tour } from "../tours"
import { HISTORY } from "./common"

// "dossiers-new" renders for editors only; "dossiers-list" only when the case has a dossier that matches the filters;
// "dossiers-detail-tabs" only while a dossier is open. Each is skipped when absent.
export const DOSSIERS_TOUR: Tour = {
  area: "dossiers",
  name: "Dossiers",
  steps: [
    { title: "One dossier per subject", body: "Start a dossier for a person, organisation, device, vehicle, address or event. Your work on that subject collects there.", targets: ['[data-guide="dossiers-new"]', "main h1"] },
    { title: "Dossiers and phone identities", body: "Phone identities lists the numbers, addresses and accounts found on the phones, so you can link each to a person.", targets: ['[data-guide="dossiers-views"]'] },
    { title: "Find a subject", body: "Search by name, or narrow by subject type and graph linkage. Archived dossiers stay hidden until you include them.", targets: ['[data-guide="dossiers-filters"]'] },
    { title: "Open a dossier", body: "Click a subject to open its dossier. A warning shows when its graph link needs review.", targets: ['[data-guide="dossiers-list"]'] },
    { title: "Brief, media and interviews", body: "Each dossier has a brief, media, assessments and interviews, each on its own tab.", targets: ['[data-guide="dossiers-detail-tabs"]'] },
    HISTORY,
  ],
}
