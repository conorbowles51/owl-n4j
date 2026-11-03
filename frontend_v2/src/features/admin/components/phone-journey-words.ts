import type { UxFunnels } from "./PhoneJourneys"

/** Journey names from the phone experience plan (07 section 3). */
export const JOURNEY_WORDS: Record<string, string> = {
  "J-1": "Add a phone and know it arrived whole",
  "J-2": "First look at a phone",
  "J-3": "Everything with one person, or between two",
  "J-4": "Read a conversation around a date",
  "J-5": "Reconstruct the window around a moment",
  "J-6": "Search everything and read the hit in context",
  "J-7": "Who is who: link identities and set owners",
  "J-8": "Check the system's readings",
  "J-9": "Test a statement against the phones",
  "J-10": "Where was the phone, and were two people together",
  "J-11": "Find deleted or concealed material",
  "J-12": "Build the case while reading",
  "J-13": "Share the review and know what is left",
  "J-14": "Export for counsel",
  "J-15": "Resume and hand over",
  "J-16": "Compare phones for a person or a pair",
  "J-17": "Explain a finding",
}

export function funnelLine(j: UxFunnels["journeys"][number]): string {
  const steps = j.steps.map((s) => `step ${s.step}: ${s.reached.toLocaleString("en-US")}`).join(" · ")
  return steps || "no steps recorded"
}
