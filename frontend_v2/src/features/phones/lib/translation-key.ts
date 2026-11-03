/** A short fingerprint of a text (FNV-1a, 32 bits, with the length): it tells one text in effect from another for a
 * cache key, nothing more. Not a security hash; plain-http pages have no `crypto.subtle`. */
export function textPrint(text: string | null | undefined): string {
  const s = text ?? ""
  let h = 0x811c9dc5
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i)
    h = Math.imul(h, 0x01000193) >>> 0
  }
  return `${s.length}:${h.toString(16)}`
}

/** The query key of one source's machine translation (05 17.5), per text in effect: when the original is corrected
 * (the message re-read, or the transcript corrected) the key changes, so the translation shown is the server's
 * answer for the corrected text, marked made from an earlier text, never a cached answer for the old one.
 * `["phone-translation", caseId]` refreshes every one shown. */
export const translationKey = (caseId: string, sourceKey: string, sourceText: string | null | undefined) => [
  "phone-translation",
  caseId,
  sourceKey,
  textPrint(sourceText),
]
