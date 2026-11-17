import type { Tour } from "../tours"
import { HISTORY } from "./common"

// "table-grid" and "table-select" render only when an entity matches the filters (and "table-select" while the
// checkbox column is shown); "table-bulk" renders only while rows are ticked, so on a first visit the tick-box
// in the header is the target.
export const TABLE_TOUR: Tour = {
  area: "table",
  name: "Table",
  steps: [
    { title: "Every entity in rows", body: "Each row is a person, company, account or other entity found in the case. Click a row to see its details.", targets: ['[data-guide="table-grid"]', "main"] },
    { title: "Search and filter", body: "Search the entities, filter by type and choose which columns to show. Click a column heading to sort.", targets: ['[data-guide="table-toolbar"]'] },
    { title: "Work on several at once", body: "Tick rows to merge duplicates, edit them together or delete them.", targets: ['[data-guide="table-bulk"]', '[data-guide="table-select"]'] },
    { title: "Take the rows with you", body: "Export CSV saves every row that matches your filters, with the columns you show.", targets: ['[data-guide="table-export"]'] },
    HISTORY,
  ],
}
