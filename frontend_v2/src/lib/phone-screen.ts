/** Which phone screen an address is (the `screen` of a report, ux-event-fields.json), or null on any other page. */
export function phoneScreen(pathname: string): string | null {
  const parts = pathname.replace(/\/+$/, "").split("/").filter(Boolean)
  if (parts[0] !== "cases" || !parts[1] || !parts[2]) return null
  const [view, sub, kind, type] = parts.slice(2)
  switch (view) {
    case "conversations":
    case "phone-review":
    case "phone-patterns":
      return view
    case "phone-money":
    case "phone-analyses":
      return "phone-analyses"
    case "search":
    case "keyword-lists":
      return "search"
    case "records":
      return "phone-records"
    case "phones":
      if (!sub) return "phones"
      if (kind !== "records") return "phone-summary"
      return type === "conversations" ? "conversations" : type === "media" ? "media" : "phone-records"
    default:
      return null
  }
}
