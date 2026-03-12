import { useMemo } from "react"
import type { GraphNode } from "@/types/graph.types"

export interface TableColumn {
  key: string
  label: string
  fixed: boolean
  sortable: boolean
  defaultVisible: boolean
}

const FIXED_COLUMNS: TableColumn[] = [
  { key: "_checkbox", label: "", fixed: true, sortable: false, defaultVisible: true },
  { key: "label", label: "Name", fixed: true, sortable: true, defaultVisible: true },
  { key: "type", label: "Type", fixed: true, sortable: true, defaultVisible: true },
  { key: "confidence", label: "Confidence", fixed: true, sortable: true, defaultVisible: true },
  { key: "summary", label: "Summary", fixed: true, sortable: true, defaultVisible: true },
  { key: "connections", label: "Connections", fixed: true, sortable: true, defaultVisible: true },
  { key: "sources", label: "Sources", fixed: true, sortable: true, defaultVisible: true },
]

const FIXED_KEYS = new Set(FIXED_COLUMNS.map((c) => c.key))
// Property keys to exclude from dynamic columns (internal/positional)
const EXCLUDED_PROPS = new Set(["x", "y", "fx", "fy", "vx", "vy", "index"])

export function useTableColumns(nodes: GraphNode[]) {
  const dynamicColumns = useMemo(() => {
    const propKeys = new Set<string>()
    for (const node of nodes) {
      for (const key of Object.keys(node.properties)) {
        if (!FIXED_KEYS.has(key) && !EXCLUDED_PROPS.has(key)) {
          propKeys.add(key)
        }
      }
    }
    return Array.from(propKeys)
      .sort()
      .map(
        (key): TableColumn => ({
          key: `prop:${key}`,
          label: key.charAt(0).toUpperCase() + key.slice(1).replace(/_/g, " "),
          fixed: false,
          sortable: true,
          defaultVisible: false,
        })
      )
  }, [nodes])

  const allColumns = useMemo(
    () => [...FIXED_COLUMNS, ...dynamicColumns],
    [dynamicColumns]
  )

  return { allColumns, fixedColumns: FIXED_COLUMNS, dynamicColumns }
}
