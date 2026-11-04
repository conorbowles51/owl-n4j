import { useEffect } from "react"
import type { MediaItem } from "../api"

/** Thumbnail sizes for the Media grid: the tile's minimum width and the picture's height. */
export const THUMB_SIZES = {
  small: { label: "Small", grid: "grid-cols-[repeat(auto-fill,minmax(6rem,1fr))]", height: "h-20" },
  medium: { label: "Medium", grid: "grid-cols-[repeat(auto-fill,minmax(9rem,1fr))]", height: "h-28" },
  large: { label: "Large", grid: "grid-cols-[repeat(auto-fill,minmax(14rem,1fr))]", height: "h-48" },
} as const
export type ThumbSize = keyof typeof THUMB_SIZES
export const THUMB_KEY = "loupe.media.thumb"
export const BLUR_KEY = "loupe.media.blur"

export function storedThumbSize(): ThumbSize {
  const v = localStorage.getItem(THUMB_KEY)
  return v === "small" || v === "large" ? v : "medium"
}

/** Blur for this person: their own choice when they made one on this screen, else the case default. */
export function blurFor(stored: string | null, caseDefault: boolean | undefined) {
  if (stored === "on") return true
  if (stored === "off") return false
  return caseDefault ?? true
}

/** The file list as tab-separated lines with a header: file, phone, category, time, state, SHA-256, MD5. */
export function fileListText(items: MediaItem[]) {
  const clean = (v: string | null | undefined) => (v ?? "").replace(/[\t\r\n]+/g, " ")
  const rows = items.map((it) => [it.filename, it.phone_label, it.category ?? "", it.taken_or_sent.full, it.verification_words,
    it.hashes?.sha256 ?? "", it.hashes?.md5 ?? ""].map(clean).join("\t"))
  return ["File\tPhone\tCategory\tTime\tState\tSHA-256\tMD5", ...rows].join("\n") + "\n"
}

/** Copy text without the clipboard API (unavailable over plain http): a hidden textarea and the copy command.
 * Returns false when the browser refused, so the caller can show the text to copy by hand. */
export function copyText(text: string) {
  const ta = document.createElement("textarea")
  ta.value = text
  ta.setAttribute("readonly", "")
  ta.style.position = "fixed"
  ta.style.opacity = "0"
  document.body.appendChild(ta)
  ta.select()
  let ok = false
  try {
    ok = document.execCommand("copy")
  } catch {
    ok = false
  }
  document.body.removeChild(ta)
  return ok
}

export function saveBlob(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = name
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  setTimeout(() => URL.revokeObjectURL(url), 60_000)
}

export function sizeWords(bytes: number) {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)} GB`
  if (bytes >= 1024 ** 2) return `${Math.round(bytes / 1024 ** 2).toLocaleString("en-US")} MB`
  return `${Math.max(1, Math.round(bytes / 1024)).toLocaleString("en-US")} KB`
}

/** A day typed in a date box as the instant it starts, in UTC (the Media dates are UTC days). */
export function dayStart(day: string, plusDays = 0) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) return undefined
  const t = Date.parse(`${day}T00:00:00Z`)
  return Number.isNaN(t) ? undefined : new Date(t + plusDays * 86_400_000).toISOString()
}

/** Left and right arrow keys move to the previous and next file while the viewer is open, except while typing. */
export function useArrowKeys(active: boolean, onPrev: (() => void) | null, onNext: (() => void) | null) {
  useEffect(() => {
    if (!active) return
    const h = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null
      if (t && (t.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName))) return
      if (e.key === "ArrowLeft" && onPrev) { e.preventDefault(); onPrev() }
      if (e.key === "ArrowRight" && onNext) { e.preventDefault(); onNext() }
    }
    window.addEventListener("keydown", h)
    return () => window.removeEventListener("keydown", h)
  }, [active, onPrev, onNext])
}
