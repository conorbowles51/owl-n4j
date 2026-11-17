import type { Tour } from "../tours"
import { HISTORY } from "./common"

// "settings-export" renders for the case's owner and the system owner only; absent for others, so it is skipped.
// The AI costs and Guidance cards (owners and admins) have no step, to keep the tour within six.
export const SETTINGS_TOUR: Tour = {
  area: "settings",
  name: "Case settings",
  steps: [
    { title: "The case's details", body: "Set the case title, description and status. Saved changes are recorded in the audit log.", targets: ['[data-guide="settings-details"]', "main h1"] },
    { title: "Addresses on the map", body: "Choose how addresses found in the evidence are placed on the map. Only the case's owner or an admin can change this.", targets: ['[data-guide="settings-address"]'] },
    { title: "Blur phone pictures", body: "Choose whether pictures from phones are blurred in Media until opened. Each person can still turn blur off for themselves.", targets: ['[data-guide="settings-blur"]'] },
    { title: "Settings for the phones", body: "Set the time zone phone times are shown in, and whether a phone's material may go to outside services.", targets: ['[data-guide="settings-phones"]'] },
    { title: "Export the whole case", body: "Build the package to move or copy this case, whole, to another Loupe installation.", targets: ['[data-guide="settings-export"]'] },
    HISTORY,
  ],
}
