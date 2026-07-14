import type { GraphLink, GraphNode, PhoneReport } from "../../types"
import { asText, readList, readNumber, readText, reportTitle } from "../shared/cellebrite-format"

export const NODE_COLORS = {
  PhoneReport: "#059669",
  Person: "#3b82f6",
  PersonShared: "#0c9da0",
}

export type ForceGraphNode = GraphNode & { id: string }
export type ForceGraphLink = GraphLink & { source: string; target: string }

export function graphNodeId(node: GraphNode): string {
  return readText(node, ["id", "key", "node_key", "label", "name"], "node")
}

export function graphEndpointId(value: string | number | GraphNode | undefined): string {
  if (typeof value === "string" || typeof value === "number") return String(value)
  return value ? graphNodeId(value) : ""
}

export function nodeType(node: GraphNode): string {
  return readText(node, ["type", "label_type", "kind"], "Person")
}

export function nodeLabel(node: GraphNode): string {
  return readText(node, ["name", "display_name", "label", "phone", "id", "key"], graphNodeId(node))
}

export function nodePhone(node: GraphNode): string {
  return readText(node, ["phone", "phone_number", "number", "identifier"])
}

export function nodeReportKeys(node: GraphNode): string[] {
  const keys = new Set<string>()
  for (const key of readList(node, ["report_keys", "device_report_keys", "reports"])) {
    keys.add(key)
  }
  const single = readText(node, ["report_key", "cellebrite_report_key", "device_report_key"])
  if (single) keys.add(single)
  return [...keys]
}

export function nodePrimaryReportKey(node: GraphNode): string {
  return readText(node, ["report_key", "cellebrite_report_key", "device_report_key"]) || nodeReportKeys(node)[0] || ""
}

export function nodeCommCount(node: GraphNode): number {
  return readNumber(node, ["comm_count", "communication_count", "message_count", "count"], 0)
}

export function isSharedNode(node: GraphNode): boolean {
  return Boolean(node.shared) || readNumber(node, ["device_count", "report_count"], 0) > 1 || nodeReportKeys(node).length > 1
}

export function reportShortLabel(report: PhoneReport): string {
  return typeof report.display_index === "number" ? `P${report.display_index + 1}` : reportTitle(report).slice(0, 3)
}

export function normalizeGraph(nodes: GraphNode[], links: GraphLink[]) {
  const normalizedNodes = nodes.map((node) => ({ ...node, id: graphNodeId(node) }))
  const nodeIds = new Set(normalizedNodes.map((node) => node.id))
  const normalizedLinks: ForceGraphLink[] = []

  for (const link of links) {
    const source = graphEndpointId(link.source)
    const target = graphEndpointId(link.target)
    if (!source || !target || !nodeIds.has(source) || !nodeIds.has(target)) continue
    normalizedLinks.push({ ...link, source, target })
  }

  return { nodes: normalizedNodes, links: normalizedLinks }
}

export function filterGraphByReportKeys(nodes: GraphNode[], links: GraphLink[], reportKeys: string[] | null) {
  if (!reportKeys?.length) return normalizeGraph(nodes, links)

  const allowed = new Set(reportKeys)
  const visibleNodes = nodes.filter((node) => {
    const type = nodeType(node)
    const keys = nodeReportKeys(node)
    if (type === "PhoneReport") {
      const key = readText(node, ["report_key", "id", "key"])
      return key ? allowed.has(key) : true
    }
    return keys.length === 0 || keys.some((key) => allowed.has(key))
  })
  return normalizeGraph(visibleNodes, links)
}

export function filterGraphBySearch(nodes: ForceGraphNode[], links: ForceGraphLink[], search: string) {
  const term = search.trim().toLowerCase()
  if (!term) return { nodes, links }

  const matchingNodeIds = new Set(
    nodes
      .filter((node) =>
        [
          nodeLabel(node),
          nodePhone(node),
          readText(node, ["email", "identifier", "imei", "phone_owner"]),
        ]
          .join(" ")
          .toLowerCase()
          .includes(term)
      )
      .map((node) => node.id)
  )

  for (const link of links) {
    if (matchingNodeIds.has(link.source)) matchingNodeIds.add(link.target)
    if (matchingNodeIds.has(link.target)) matchingNodeIds.add(link.source)
  }

  return {
    nodes: nodes.filter((node) => matchingNodeIds.has(node.id)),
    links: links.filter((link) => matchingNodeIds.has(link.source) && matchingNodeIds.has(link.target)),
  }
}

export function linkWeight(link: GraphLink): number {
  return readNumber(link, ["count", "weight", "value"], 1)
}

export function sharedContactSearchText(row: Record<string, unknown>): string {
  return [
    readText(row, ["name", "display_name", "label", "phone"]),
    readList(row, ["report_keys", "devices"]).join(" "),
    asText(row.count),
  ].join(" ")
}
