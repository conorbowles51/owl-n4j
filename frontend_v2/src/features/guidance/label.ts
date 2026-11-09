import type { QueryClient } from "@tanstack/react-query"

/**
 * A plain label for an id, from data already loaded in this tab (no request): the first loaded object whose id or
 * key is this id, by its name, label, title or file name. Null when nothing loaded names it.
 */
export function labelFromCache(qc: QueryClient, id: string): string | null {
  if (!id) return null
  let budget = 20_000
  const NAME_FIELDS = ["display_name", "name", "label", "title", "original_filename", "file_name", "filename", "description"]
  const walk = (v: unknown, depth: number): string | null => {
    if (budget-- <= 0 || depth > 5 || !v || typeof v !== "object") return null
    if (Array.isArray(v)) {
      for (const x of v) {
        const found = walk(x, depth + 1)
        if (found) return found
      }
      return null
    }
    const o = v as Record<string, unknown>
    if (o.id === id || o.key === id || o.node_key === id || o.account_id === id) {
      const number = typeof o.account_number === "string" ? o.account_number : null
      const bank = typeof o.bank_name === "string" ? o.bank_name : typeof o.institution === "string" ? o.institution : null
      if (number) return [bank, number].filter(Boolean).join(" ")
      for (const f of NAME_FIELDS) if (typeof o[f] === "string" && (o[f] as string).trim()) return (o[f] as string).trim().slice(0, 120)
    }
    for (const x of Object.values(o)) {
      if (x && typeof x === "object") {
        const found = walk(x, depth + 1)
        if (found) return found
      }
    }
    return null
  }
  for (const q of qc.getQueryCache().getAll()) {
    const found = walk(q.state.data, 0)
    if (found) return found
    if (budget <= 0) break
  }
  return null
}
