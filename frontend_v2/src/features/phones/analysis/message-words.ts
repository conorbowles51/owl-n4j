import type { ApproachResult } from "./analysis-api"

export const TABS = [
  { kind: "both_sides", label: "On both phones" },
  { kind: "deleted_one_side", label: "Deleted on one phone" },
  { kind: "one_side_only", label: "On one phone only" },
  { kind: "ambiguous_pair", label: "Two equally close copies" },
  { kind: "clock_offset", label: "Clocks" },
]

type M = Record<string, unknown>
const secs = (v: unknown) => {
  const s = Math.abs(Number(v ?? 0))
  return `${Math.round(s).toLocaleString("en-US")} second${Math.round(s) === 1 ? "" : "s"}`
}
const TIER_WORDS: Record<string, string> = {
  matched_strong: "Sender and recipient agree with the two phones' owners.",
  matched_content_time: "Text and time agree; one copy does not name its sender.",
}

/** Words for approach 2's results (05 section 5.4). Never says who wrote, read or deleted anything. */
export function messageWords(r: ApproachResult) {
  const m = r.measures as M
  const [x, y] = ((m.phones as string[]) || ["", ""])
  if (r.kind === "both_sides") {
    const off = Number(m.offset_s ?? 0) ? ` after a clock offset of ${secs(m.offset_s)}` : ""
    return { title: `Message on ${x} and ${y}`, line: `${secs(m.seconds_apart)} apart${off}. ${TIER_WORDS[r.strength] ?? ""}`.trim() }
  }
  if (r.kind === "deleted_one_side") {
    const [dx] = (m.deleted as boolean[]) || [false, false]
    const gone = dx ? x : y
    return { title: `Deleted on ${gone}, still on ${m.recovered_from}`,
      line: `The text is read from ${m.recovered_from}'s copy; ${gone}'s record is unchanged. ${secs(m.seconds_apart)} apart. ${TIER_WORDS[r.strength] ?? ""}`.trim() }
  }
  if (r.kind === "one_side_only") {
    const reasons = r.directions.undercuts.map((d) => d.detail)
    return { title: `On ${m.on}, no copy found on ${m.not_on}`,
      line: reasons.length ? reasons.join(" ") : `No reason found in the records why ${m.not_on} has no copy.` }
  }
  if (r.kind === "ambiguous_pair") {
    return { title: `${Number(m.candidates ?? 2)} equally close copies between ${x} and ${y}`, line: "Neither copy is chosen; open the records to compare them." }
  }
  return { title: `Clocks of ${x} and ${y} (${m.family})`, line: String(m.words ?? "") }
}
