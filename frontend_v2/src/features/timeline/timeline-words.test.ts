import { expect, it } from "vitest"

// Phone records (calls, messages) come to the Timeline: "phone" in its code means phone data, never a narrow
// screen (spec 07, finding 14). A narrow layout is called a narrow screen.
const sources = import.meta.glob(["./**/*.ts", "./**/*.tsx", "!./**/*.test.ts", "!./**/*.test.tsx", "!./lens/**"], {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>

// The phone lens (03 section 9) is phone data: its folder and the names that load it are allowed.
const PHONE_DATA = /phone lens|phone entr(y|ies)|phone data|phones' own|getPhones|PhoneLens\w*|features\/phones\/\S*|phone list|a phone|phone \(\w+\)/gi

it("says narrow screen, not phone, for a narrow layout", () => {
  const found = Object.entries(sources).flatMap(([path, text]) =>
    text.split("\n").flatMap((line, n) =>
      /\b(phone|mobile)\b/i.test(line.replace(/PhoneCall/g, "").replace(PHONE_DATA, "")) ? [`${path}:${n + 1}: ${line.trim()}`] : []
    )
  )
  expect(Object.keys(sources).length).toBeGreaterThan(5)
  expect(found).toEqual([])
})
