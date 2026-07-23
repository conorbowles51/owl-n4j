export const nodeColors = {
  person: "#5571C8",
  organization: "#8060A9",
  location: "#238A88",
  financial: "#B37A2E",
  document: "#72757E",
  event: "#C25778",
  communication: "#2C8197",
  vehicle: "#6F8B45",
  digital: "#765FA6",
  evidence: "#C4653F",
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

const FALLBACK_COLOR = "#72757E"

/** Case-insensitive entity type -> color lookup with alias mapping and hash fallback */
export function getNodeColor(type: string): string {
  if (!type) return FALLBACK_COLOR
  const lower = type.toLowerCase()

  if (lower in nodeColors) return nodeColors[lower as EntityType]

  const alias = typeAliases[lower]
  if (alias) return nodeColors[alias]

  let hash = 0
  for (let i = 0; i < lower.length; i++) {
    hash = lower.charCodeAt(i) + ((hash << 5) - hash)
  }
  const palette = Object.values(nodeColors)
  return palette[Math.abs(hash) % palette.length]
}

export const statusColors = {
  success: { bg: "#E1F1E9", text: "#286A4E", dot: "#3B8B67" },
  danger: { bg: "#F9E5E7", text: "#9C313C", dot: "#BE4652" },
  warning: { bg: "#F9EED6", text: "#815F25", dot: "#AD7D2D" },
  info: { bg: "#E5EDF6", text: "#315E86", dot: "#4A7DA8" },
  amber: { bg: "#FFE4E8", text: "#941B27", dot: "#B41624" },
  slate: { bg: "#EFEFF1", text: "#565961", dot: "#9A9DA5" },
} as const

export type StatusVariant = keyof typeof statusColors

/** Canvas/WebGL colors that adapt to light/dark mode */
export function getCanvasColors(isDark: boolean) {
  return {
    background: isDark ? "#090A0D" : "#F5F5F6",
    linkColor: isDark ? "#34363E" : "#DADBE0",
    labelText: isDark ? "#BFC1C8" : "#565961",
    labelBg: isDark ? "rgba(11,12,15,0.9)" : "rgba(247,247,248,0.94)",
    hoverStroke: isDark ? "#9A9DA5" : "#71747C",
    selectionStroke: isDark ? "#F35D6D" : "#B41624",
    selectionGlow: isDark ? "rgba(243,93,109,0.3)" : "rgba(180,22,36,0.2)",
    statsOverlayBg: isDark ? "rgba(23,24,28,0.9)" : "rgba(247,247,248,0.94)",
    statsOverlayText: isDark ? "#9A9DA5" : "#71747C",
  }
}
