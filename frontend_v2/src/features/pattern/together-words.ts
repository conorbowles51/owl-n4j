/**
 * Plain words for the kinds of evidence a Together run compares (04 section 8.4) and the cautions on them.
 * `counts` is the run's counts object: `basis:<name>` and `flag:<name>` keys (backend colocation.compute).
 */
export const BASIS_WORDS: Record<string, string> = {
  coordinates: "from recorded positions",
  shared_bssid: "from the same Wi-Fi network seen by both phones",
  shared_cell: "from the same cell tower seen by both phones (a wide area)",
  bluetooth: "from one phone's Bluetooth seeing the other phone (about 30 m)",
}

export function evidenceWords(counts: Record<string, number> | undefined): string[] {
  const c = counts || {}
  const out: string[] = []
  for (const [basis, words] of Object.entries(BASIS_WORDS)) {
    const n = c[`basis:${basis}`] || 0
    if (!n) continue
    let line = `${n.toLocaleString()} ${words}`
    if (basis === "shared_cell" && c["flag:mcc_inferred"]) {
      const m = c["flag:mcc_inferred"]
      line += `; ${m.toLocaleString()} of them ${m === 1 ? "uses" : "use"} a country code taken from the phone's SIM card, because the tower record does not state one`
    }
    if (basis === "bluetooth") {
      const byName = c["flag:name_match"] || 0
      const nearby = c["flag:nearby_not_connected"] || 0
      if (byName) line += `; ${byName.toLocaleString()} matched by device name only, which anyone can set, so never counted as close together`
      if (nearby) line += `; ${nearby.toLocaleString()} nearby, not connected (a scan saw the device)`
    }
    out.push(line + ".")
  }
  const defaults = c["not_compared:default_device_name"] || 0
  if (defaults) {
    out.push(`${defaults.toLocaleString()} Bluetooth ${defaults === 1 ? "sighting" : "sightings"} not compared: the other phone's Bluetooth name is its factory default (its model name), which every phone of that model shares.`)
  }
  return out
}

/** The allowances a Together run used, from the run itself; a run that does not state one says nothing about it. */
export function allowanceWords(params: Record<string, unknown> | undefined): string[] {
  const radius = Number(params?.assumed_radius_m), speed = Number(params?.max_speed_mps)
  const out: string[] = []
  if (radius > 0) out.push(`A position with no accuracy uses an assumed radius of ${radius.toLocaleString("en-US")} m and is marked.`)
  if (speed > 0) out.push(`Two positions are separated only if travelling between them would take more than ${(Math.round(speed * 36) / 10).toLocaleString("en-US")} km/h.`)
  return out
}

/** Unplaced cell towers whose country code came from the SIM, said once. */
export function towerMccWords(towers: { mcc_inferred?: boolean }[], words?: string | null): string | null {
  const n = towers.filter((t) => t.mcc_inferred).length
  if (!n || !words) return null
  return `${n.toLocaleString()} of these towers: ${words}`
}
