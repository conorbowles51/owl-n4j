import { expect, it } from "vitest"

// Phone records (calls, messages) come to the Timeline: "phone" in its code means phone data, never a narrow
// screen (spec 07, finding 14). A narrow layout is called a narrow screen.
const sources = import.meta.glob(["./**/*.ts", "./**/*.tsx", "!./**/*.test.ts", "!./**/*.test.tsx"], {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>

it("says narrow screen, not phone, for a narrow layout", () => {
  const found = Object.entries(sources).flatMap(([path, text]) =>
    text.split("\n").flatMap((line, n) =>
      /\b(phone|mobile)\b/i.test(line.replace(/PhoneCall/g, "")) ? [`${path}:${n + 1}: ${line.trim()}`] : []
    )
  )
  expect(Object.keys(sources).length).toBeGreaterThan(5)
  expect(found).toEqual([])
})
