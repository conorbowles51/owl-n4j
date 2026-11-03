import type { ApproachResult } from "./analysis-api"

export const TABS = [
  { kind: "shared_markers", label: "In common" },
  { kind: "complementary_use", label: "Used in turn" },
  { kind: "more_than_one_user", label: "Signs of more than one user" },
]

const KIND_WORDS: Record<string, [string, string]> = {
  owner_number: ["owner phone number", "owner phone numbers"], iccid: ["SIM card number", "SIM card numbers"],
  imsi: ["SIM subscriber number", "SIM subscriber numbers"], account: ["account username on one service", "account usernames on one service"],
  saved_login: ["saved-login account on one service", "saved-login accounts on one service"], wifi_bssid: ["WiFi access point", "WiFi access points"],
}
const STRENGTH_WORDS: Record<string, string> = { strong: "strong", medium: "medium", weak: "weak (families and workplaces share networks)" }

type M = Record<string, unknown>
const n = (v: unknown) => Number(v ?? 0).toLocaleString("en-US")

export function deviceWords(r: ApproachResult) {
  const m = r.measures as M
  const pair = ((m.phones as string[]) || []).join(" and ")
  if (r.kind === "shared_markers") {
    const kinds = Object.entries((m.by_kind || {}) as Record<string, number>).map(([k, c]) => `${c} ${KIND_WORDS[k] ? KIND_WORDS[k][c === 1 ? 0 : 1] : k}`)
    return { title: `${pair} have ${kinds.join(", ")} in common`, line: `Strongest kind: ${STRENGTH_WORDS[r.strength] || r.strength}. The values are compared on the server and not shown here; open the records to see them.` }
  }
  if (r.kind === "complementary_use") {
    const [x, y] = (m.phones as string[]) || ["", ""]
    return { title: `${pair}: ${n(m.days)} days with use on both`,
      line: `Quarter hours with both in use ${n(m.both)}, only ${x} ${n(m.only_x)}, only ${y} ${n(m.only_y)}, neither ${n(m.neither)}. Phi ${m.phi ?? "not computed"}; ${m.switches_per_day ?? 0} switches a day from one phone to the other within an hour. From ${m.first_day} to ${m.last_day}.` }
  }
  return { title: `Signs of more than one user on ${m.phone_label}`, line: `${((m.signs as string[]) || []).join("; ")}. Listed, not scored.` }
}
