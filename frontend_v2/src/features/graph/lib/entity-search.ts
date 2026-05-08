import Fuse from "fuse.js"
import type { IFuseOptions } from "fuse.js"
import type { GraphNode } from "@/types/graph.types"

const fuseOptions: IFuseOptions<GraphNode> = {
  keys: [
    { name: "label", weight: 0.55 },
    { name: "aliases", weight: 0.3 },
    { name: "type", weight: 0.05 },
    { name: "summary", weight: 0.05 },
    { name: "notes", weight: 0.025 },
    {
      name: "_propsText",
      weight: 0.025,
      getFn: (node: GraphNode) =>
        Object.values(node.properties)
          .filter((v) => typeof v === "string" || typeof v === "number")
          .map(String)
          .join(" "),
    },
  ],
  threshold: 0.3,
  ignoreLocation: true,
  minMatchCharLength: 2,
  includeScore: false,
}

export function buildEntityFuse(nodes: GraphNode[]): Fuse<GraphNode> {
  return new Fuse(nodes, fuseOptions)
}

export function filterNodesBySearch(
  nodes: GraphNode[],
  term: string,
  fuse: Fuse<GraphNode>
): GraphNode[] {
  const trimmed = term.trim()
  if (!trimmed) return nodes
  if (trimmed.length < 2) return nodes
  const matched = fuse.search(trimmed).map((r) => r.item)
  const survivors = new Set(nodes)
  return matched.filter((n) => survivors.has(n))
}
