import type { ApproachResult } from "./analysis-api"
import { LEVEL_WORDS, reasonWords } from "./strength-words"

export const TABS = [
  { kind: "shared_key", label: "Shared across phones" },
  { kind: "phone_inventory", label: "Each phone" },
  { kind: "service_without_app", label: "Services without an app" },
  { kind: "remote_session", label: "Remote sessions" },
]

type M = Record<string, unknown>
type PhoneHold = { phone_label: string; records: number; events: number; natures: string[]; nearby_only: boolean; first: string | null; last: string | null }
const n = (v: unknown) => Number(v ?? 0).toLocaleString("en-US")
const KEY_WORDS: Record<string, [string, string]> = {
  wifi_bssid: ["WiFi access point", "WiFi access points"], bluetooth_address: ["Bluetooth device address", "Bluetooth device addresses"],
  owner_number: ["owner phone number", "owner phone numbers"], iccid: ["SIM card number", "SIM card numbers"], imsi: ["SIM subscriber number", "SIM subscriber numbers"],
  account: ["account username on one service", "account usernames on one service"], saved_login: ["saved-login account on one service", "saved-login accounts on one service"],
  ssid: ["WiFi network name", "WiFi network names"], bluetooth_name: ["Bluetooth device name", "Bluetooth device names"], service: ["web service", "web services"],
}

const holdWords = (p: PhoneHold) =>
  `${p.phone_label}: ${n(p.events)} ${p.events === 1 ? "record" : "records"}${p.nearby_only ? ", nearby, not connected" : ""}${p.natures.length ? ` (${p.natures.join(", ")})` : ""}`

export function otherDevicesWords(r: ApproachResult) {
  const m = r.measures as M
  if (r.kind === "shared_key") {
    const phones = (m.phones as PhoneHold[]) || []
    const what = KEY_WORDS[m.key_kind as string]?.[0] ?? String(m.key_kind)
    const value = m.value ? ` ${m.value}` : ""
    return {
      title: `${LEVEL_WORDS[r.strength] ?? r.strength}: the same ${what}${value} on ${phones.map((p) => p.phone_label).join(" and ")}`,
      line: `${phones.map(holdWords).join("; ")}. ${reasonWords(m)}${m.value ? "" : " The value is compared on the server and not shown here; open the records to see it."}`,
    }
  }
  if (r.kind === "phone_inventory") {
    const by = (m.keys_by_kind || {}) as Record<string, number>
    const parts = Object.entries(by).map(([k, c]) => `${n(c)} ${KEY_WORDS[k] ? KEY_WORDS[k][c === 1 ? 0 : 1] : k}`)
    return {
      title: `${m.phone_label}: devices, networks, accounts and services`,
      line: `${parts.length ? parts.join(", ") : "None recorded"}.${Number(m.bluetooth_nearby_only) ? ` ${n(m.bluetooth_nearby_only)} Bluetooth devices only nearby, not connected.` : ""} ${m.apps_compared ? `Services compared with ${n(m.installed_apps)} installed apps.` : String(m.no_app_words ?? "")}`,
    }
  }
  if (r.kind === "service_without_app") {
    return { title: `${LEVEL_WORDS[r.strength] ?? r.strength}: ${m.service} on ${m.phone_label}, no app for it installed`, line: reasonWords(m) }
  }
  return {
    title: `Remote session on ${m.phone_label}: ${[m.device_family, m.os].filter(Boolean).join(", ") || "device not read from the user agent"}`,
    line: m.started ? `Started ${m.started}.` : "No start time recorded.",
  }
}
