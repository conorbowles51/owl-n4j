export interface TableColumn {
  key: string
  label: string
  fixed: boolean
  sortable: boolean
  defaultVisible: boolean
}

const ALL_COLUMNS: TableColumn[] = [
  { key: "_checkbox", label: "", fixed: true, sortable: false, defaultVisible: true },
  { key: "label", label: "Name", fixed: true, sortable: true, defaultVisible: true },
  { key: "type", label: "Type", fixed: false, sortable: true, defaultVisible: true },
  { key: "connections", label: "Connections", fixed: false, sortable: true, defaultVisible: true },
  { key: "sources", label: "Sources", fixed: false, sortable: true, defaultVisible: true },
  { key: "prop:amount", label: "Amount", fixed: false, sortable: true, defaultVisible: true },
  { key: "prop:date", label: "Date", fixed: false, sortable: true, defaultVisible: true },
  { key: "prop:file_name", label: "File Name", fixed: false, sortable: true, defaultVisible: true },
  { key: "prop:location_raw", label: "Location", fixed: false, sortable: true, defaultVisible: true },
]

export function useTableColumns() {
  return { allColumns: ALL_COLUMNS, fixedColumns: ALL_COLUMNS, dynamicColumns: [] }
}
