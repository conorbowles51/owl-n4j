import * as React from "react"

/** Whether any words are drawn inside: strings and numbers count, icons and empty elements do not. */
export function hasWords(node: React.ReactNode): boolean {
  if (node === null || node === undefined || typeof node === "boolean") return false
  if (typeof node === "string") return node.trim().length > 0
  if (typeof node === "number" || typeof node === "bigint") return true
  if (Array.isArray(node)) return node.some(hasWords)
  if (React.isValidElement(node)) {
    const p = node.props as { children?: React.ReactNode; className?: string }
    if (typeof p.className === "string" && /\bsr-only\b/.test(p.className)) return false
    return hasWords(p.children)
  }
  return true
}
