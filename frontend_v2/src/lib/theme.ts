export const nodeColors = {
  person: "#6366F1",
  organization: "#8B5CF6",
  location: "#14B8A6",
  financial: "#F59E0B",
  document: "#64748B",
  event: "#EC4899",
  communication: "#06B6D4",
  vehicle: "#84CC16",
  digital: "#A855F7",
  evidence: "#F97316",
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

const FALLBACK_COLOR = "#64748B"

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

/** Community detection color palette */
export const communityColors = [
  "#ef4444", "#3b82f6", "#22c55e", "#f59e0b",
  "#8b5cf6", "#ec4899", "#06b6d4", "#84cc16",
  "#f97316", "#a855f7", "#14b8a6", "#eab308",
]

export const statusColors = {
  success: { bg: "#DCFCE7", text: "#15803D", dot: "#22C55E" },
  danger: { bg: "#FEE2E2", text: "#B91C1C", dot: "#EF4444" },
  warning: { bg: "#FEF9C3", text: "#A16207", dot: "#EAB308" },
  info: { bg: "#DBEAFE", text: "#1D4ED8", dot: "#3B82F6" },
  amber: { bg: "#FBF0D0", text: "#92610A", dot: "#D4920A" },
  slate: { bg: "#E8ECF1", text: "#3E4C63", dot: "#8494A7" },
} as const

export type StatusVariant = keyof typeof statusColors

/** Canvas/WebGL colors that adapt to light/dark mode */
export function getCanvasColors(isDark: boolean) {
  return {
    background: isDark ? "#0B0F1A" : "#F4F6F8",
    linkColor: isDark ? "#2D3A4F" : "#CBD5E1",
    labelText: isDark ? "#AAB7C7" : "#475569",
    labelBg: isDark ? "rgba(11,15,26,0.85)" : "rgba(244,246,248,0.9)",
    hoverStroke: isDark ? "#94A3B8" : "#64748B",
    selectionStroke: "#3B82F6",
    selectionGlow: isDark ? "rgba(59,130,246,0.25)" : "rgba(59,130,246,0.15)",
    statsOverlayBg: isDark ? "rgba(15,23,42,0.8)" : "rgba(241,245,249,0.9)",
    statsOverlayText: isDark ? "#94A3B8" : "#64748B",
  }
}
