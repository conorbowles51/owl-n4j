import type { Tour } from "../tours"
import { HISTORY } from "./common"

export const REPORTS_TOUR: Tour = {
  area: "reports",
  name: "Reports",
  steps: [
    { title: "Start a financial report", body: "New financial report opens the financial findings, where you choose the ones the report holds.", targets: ['[data-guide="reports-new"]', "text=New financial report"] },
    { title: "Saved financial reports", body: "Each saved report keeps the versions of the findings chosen when it was prepared. Open one to read it.", targets: ['[data-guide="reports-financial"]'] },
    { title: "The casework report", body: "Choose Findings, Theories and Notes and their order, pick a marking, then export them as a PDF.", targets: ['[data-guide="reports-casework"]'] },
    HISTORY,
  ],
}
