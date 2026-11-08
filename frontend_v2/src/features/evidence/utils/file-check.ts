import type { EvidenceFile } from "@/types/evidence.types"

type Checked = Pick<EvidenceFile, "original_filename" | "file_type_match" | "file_type_words" | "reading_hold" |
  "reading_hold_reason" | "reading_hold_detail" | "reading_released_by" | "reading_released_at" | "malware_scan">

/** What a mislabelled file says. The mark changes nothing about the file: it stays in the case and can be read. */
export function mismatchText(file: Checked): string | null {
  if (file.file_type_match !== "mismatch") return null
  return `The name ${file.original_filename} does not match its contents, which are a ${file.file_type_words ?? "different type of file"}. The file is kept as it arrived.`
}

/** Why a file is held from model reading, or who released it. */
export function holdText(file: Checked): string | null {
  if (!file.reading_hold) return null
  const why = file.reading_hold_reason === "malware"
    ? `The malware scan found ${file.reading_hold_detail ?? "a match"}.`
    : `This file is program code (${file.file_type_words ?? "a program"}).`
  if (file.reading_hold === "released") {
    const when = file.reading_released_at ? new Date(file.reading_released_at).toLocaleString() : ""
    return `${why} ${file.reading_released_by ?? "Someone"} released it for reading${when ? ` on ${when}` : ""}.`
  }
  return `${why} It stays in the case and is not sent for reading until someone releases it.`
}

/** What the malware scan says, when it says anything a person needs to know. */
export function scanText(file: Checked): string | null {
  if (file.malware_scan === "failed") return "The malware scan could not finish on this file, so it is not known to be clean."
  if (file.malware_scan === "waiting") return "Waiting for the malware scan."
  return null
}
