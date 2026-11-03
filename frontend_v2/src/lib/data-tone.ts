export const SOURCE_TONES = [
  { text: "text-source-1", border: "border-source-1", bg: "bg-source-1", edge: "shadow-[inset_4px_0_0_hsl(var(--source-1))]" },
  { text: "text-source-2", border: "border-source-2", bg: "bg-source-2", edge: "shadow-[inset_4px_0_0_hsl(var(--source-2))]" },
  { text: "text-source-3", border: "border-source-3", bg: "bg-source-3", edge: "shadow-[inset_4px_0_0_hsl(var(--source-3))]" },
  { text: "text-source-4", border: "border-source-4", bg: "bg-source-4", edge: "shadow-[inset_4px_0_0_hsl(var(--source-4))]" },
] as const

const hash = (s: string) => [...s].reduce((a, c) => (a * 31 + c.charCodeAt(0)) >>> 0, 7)

/** One stable colour per account or source key (the account's name is always shown beside it). */
export function sourceTone(key: string) {
  return SOURCE_TONES[hash(key || "?") % SOURCE_TONES.length]
}

const APP_TONES = [
  { text: "text-app-1", border: "border-app-1", bg: "bg-app-1", soft: "bg-app-1-soft" },
  { text: "text-app-2", border: "border-app-2", bg: "bg-app-2", soft: "bg-app-2-soft" },
  { text: "text-app-3", border: "border-app-3", bg: "bg-app-3", soft: "bg-app-3-soft" },
  { text: "text-app-4", border: "border-app-4", bg: "bg-app-4", soft: "bg-app-4-soft" },
] as const

const KNOWN_APPS: Record<string, number> = { whatsapp: 0, telegram: 1, signal: 2, "native messages": 3, sms: 3, imessage: 3 }

/** One colour per phone app, the same on every phone screen (the app's name is always shown beside it). */
export function appTone(app: string) {
  const known = KNOWN_APPS[app.trim().toLowerCase()]
  return APP_TONES[known ?? hash(app.toLowerCase()) % APP_TONES.length]
}
