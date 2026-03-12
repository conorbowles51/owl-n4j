import { useCallback } from "react"
import type { GraphNode } from "@/types/graph.types"
import type { TableColumn } from "./use-table-columns"

function escapeCSV(value: string): string {
  if (value.includes(",") || value.includes('"') || value.includes("\n")) {
    return `"${value.replace(/"/g, '""')}"`
  }
  return value
}

function getCellValue(
  node: GraphNode,
  col: TableColumn,
  connectionCounts: Map<string, number>,
  sourceCounts: Map<string, number>
): string {
  switch (col.key) {
    case "label":
      return node.label
    case "type":
      return node.type
    case "confidence":
      return node.confidence != null ? `${Math.round(node.confidence * 100)}%` : ""
    case "summary":
      return node.summary ?? ""
    case "connections":
      return String(connectionCounts.get(node.key) ?? 0)
    case "sources":
      return String(sourceCounts.get(node.key) ?? 0)
    default:
      if (col.key.startsWith("prop:")) {
        const propKey = col.key.slice(5)
        const val = node.properties[propKey]
        return val != null ? String(val) : ""
      }
      return ""
  }
}

export function useCsvExport() {
  const exportCSV = useCallback(
    ({
      nodes,
      columns,
      connectionCounts,
      sourceCounts,
      filename,
    }: {
      nodes: GraphNode[]
      columns: TableColumn[]
      connectionCounts: Map<string, number>
      sourceCounts: Map<string, number>
      filename: string
    }) => {
      const visibleCols = columns.filter((c) => c.key !== "_checkbox")

      const header = visibleCols.map((c) => escapeCSV(c.label)).join(",")
      const rows = nodes.map((node) =>
        visibleCols
          .map((col) => escapeCSV(getCellValue(node, col, connectionCounts, sourceCounts)))
          .join(",")
      )

      const csv = [header, ...rows].join("\n")
      const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" })
      const url = URL.createObjectURL(blob)
      const link = document.createElement("a")
      link.href = url
      link.download = filename
      link.click()
      URL.revokeObjectURL(url)
    },
    []
  )

  return { exportCSV }
}
