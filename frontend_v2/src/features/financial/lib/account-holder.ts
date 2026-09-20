// Match recorded names across banks without inferring an identity or alias.
export const holderKey = (name: string | undefined) =>
  (name || "").trim().replace(/\s+/g, " ").toLowerCase()
