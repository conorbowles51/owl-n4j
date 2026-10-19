/** Explain validation failures without dumping request values or raw JSON. */
export function apiErrorMessage(detail: unknown, status: number): string {
  if (typeof detail === "string") return detail
  if (
    detail &&
    typeof detail === "object" &&
    "message" in detail &&
    typeof detail.message === "string"
  )
    return detail.message
  if (Array.isArray(detail)) {
    const messages = detail.flatMap((issue: unknown) => {
      if (
        !issue ||
        typeof issue !== "object" ||
        !("msg" in issue) ||
        typeof issue.msg !== "string"
      )
        return []
      const location =
        "loc" in issue && Array.isArray(issue.loc) ? issue.loc : []
      const path = location.filter(
        (part: unknown) =>
          part !== "body" && part !== "query" && part !== "path"
      )
      if (
        path.some(
          (part) =>
            typeof part === "string" && /^(expected_.*|revision)$/.test(part)
        )
      )
        return [
          "The saved records changed. Reload this view and review the action again.",
        ]
      const label = path
        .map((part: unknown) =>
          typeof part === "number"
            ? String(part + 1)
            : typeof part === "string"
              ? part.replaceAll("_", " ")
              : ""
        )
        .filter(Boolean)
        .join(" · ")
      const message = issue.msg.replace(/^Value error,\s*/i, "")
      return [
        label
          ? `${label[0].toUpperCase()}${label.slice(1)}: ${message}`
          : message,
      ]
    })
    const unique = [...new Set(messages)]
    if (unique.length)
      return (
        unique.slice(0, 5).join(". ") +
        (unique.length > 5
          ? `. Check ${unique.length - 5} additional fields.`
          : "")
      )
  }
  return status === 422
    ? "Some fields could not be accepted. Check your entries and try again."
    : `The request could not be completed (${status}). Try again or reopen this view.`
}
