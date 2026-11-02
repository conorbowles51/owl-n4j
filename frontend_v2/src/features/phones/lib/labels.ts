import type { ParticipantLabelData } from "../schemas"

/**
 * One participant as 03 section 3.3 writes it; the same text as the server's ``labels.label_text`` so the row, copy
 * and export agree.
 */

export const NO_NAME = "(no name on this phone)"
const APP_WORDS: Record<string, string> = {
  whatsapp: "WhatsApp", telegram: "Telegram", signal: "Signal", facebook: "Facebook", messenger: "Messenger",
  instagram: "Instagram", skype: "Skype", viber: "Viber", snapchat: "Snapchat", wechat: "WeChat", line: "LINE",
  apple: "Apple", google: "Google",
}

export function identifierText(id: ParticipantLabelData["identifier"]): string | null {
  if (!id) return null
  if (id.kind === "app_user") {
    const app = APP_WORDS[(id.subkind ?? "").split("_")[0].toLowerCase()]
    return app ? `${app} id ${id.display}` : `app id ${id.display}`
  }
  return id.display
}

export function labelText(l: ParticipantLabelData | null | undefined): string {
  if (!l) return "(sender not recorded)"
  const ident = identifierText(l.identifier)
  const name = l.name
  if (l.is_owner) {
    let who = `Owner of ${l.phone_label ?? "this phone"}`
    if (l.owner_basis === "manual") who += " [Owner set by a person]"
    if (!ident) return `${who}${name ? `: ${name}` : ""} (number not in the extraction)`
    return name ? `${who}: ${name} (${ident})` : `${who} (${ident})`
  }
  if (!ident) return `${name ?? NO_NAME} (no identifier recorded)`
  return `${name ?? NO_NAME} (${ident})`
}
