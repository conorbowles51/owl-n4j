export const nodeColors = {
  person: "#4F69C6",
  organization: "#7458A6",
  location: "#0C9DA0",
  financial: "#B7791F",
  document: "#667D85",
  event: "#B55473",
  communication: "#17879E",
  vehicle: "#6F8D3C",
  digital: "#7A5BA7",
  evidence: "#C66A32",
} as const

export type EntityType = keyof typeof nodeColors

export const typeAliases: Record<string, EntityType> = {
  company: "organization",
  organisation: "organization",
  org: "organization",
  bank: "financial",
  account: "financial",
  transaction: "financial",
  transfer: "financial",
  payment: "financial",
  email: "communication",
  phonecall: "communication",
  phone_call: "communication",
  meeting: "event",
  file: "document",
  phone: "digital",
  computer: "digital",
  device: "digital",
  car: "vehicle",
  address: "location",
  place: "location",
}

const FALLBACK_COLOR = "#667D85"

/** Case-insensitive entity type → color lookup with alias mapping and hash fallback */
export function getNodeColor(type: string): string {
  if (!type) return FALLBACK_COLOR
  const lower = type.toLowerCase()

  // Direct match
  if (lower in nodeColors) return nodeColors[lower as EntityType]

  // Alias match
  const alias = typeAliases[lower]
  if (alias) return nodeColors[alias]

  // Hash-based fallback for unknown types (consistent per type)
  let hash = 0
  for (let i = 0; i < lower.length; i++) {
    hash = lower.charCodeAt(i) + ((hash << 5) - hash)
  }
  const palette = Object.values(nodeColors)
  return palette[Math.abs(hash) % palette.length]
}

export const statusColors = {
  success: { bg: "#DDF2E9", text: "#267159", dot: "#3E9B78" },
  danger: { bg: "#F9E5E7", text: "#A33D46", dot: "#C34E57" },
  warning: { bg: "#FAEFD5", text: "#8B6622", dot: "#B8892E" },
  info: { bg: "#E2EFF2", text: "#276C7A", dot: "#388FA0" },
  amber: { bg: "#DBEFEE", text: "#067278", dot: "#0C9DA0" },
  slate: { bg: "#EBF0F2", text: "#46656F", dot: "#91A2A8" },
} as const

export type StatusVariant = keyof typeof statusColors

/** Canvas/WebGL colors that adapt to light/dark mode */
export function getCanvasColors(isDark: boolean) {
  return {
    background: isDark ? "#071820" : "#F4F7F8",
    linkColor: isDark ? "#294D59" : "#D3DCDF",
    labelText: isDark ? "#B6C2C6" : "#46656F",
    labelBg: isDark ? "rgba(7,24,32,0.88)" : "rgba(244,247,248,0.92)",
    hoverStroke: isDark ? "#91A2A8" : "#667D85",
    selectionStroke: "#0C9DA0",
    selectionGlow: isDark ? "rgba(54,179,178,0.28)" : "rgba(12,157,160,0.18)",
    statsOverlayBg: isDark ? "rgba(11,32,42,0.86)" : "rgba(244,247,248,0.92)",
    statsOverlayText: isDark ? "#91A2A8" : "#667D85",
  }
}
