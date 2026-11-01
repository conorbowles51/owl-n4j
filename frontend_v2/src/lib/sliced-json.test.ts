import { expect, it } from "vitest"
import { parseJSONSliced, SLICED_MINIMUM } from "./sliced-json"

// Rows shaped like ledger payments, with the characters a scanner can get wrong: escaped quotes, backslashes
// before a closing quote, brackets and braces inside strings, 2-4 byte characters, numbers, null, nesting.
function rows(count: number) {
  return Array.from({ length: count }, (_, id) => ({
    id,
    description: `PAGO "SPEI" ${id} [ref {x}] \\ ${id % 7 === 0 ? "\\" : ""}`,
    to_name: `ARRENDO SERVICIOS AÑO ${id} 東京 💶`,
    amount: id % 3 === 0 ? -1234.5 : 1e-7 * id,
    amount_corrected: id % 11 === 0 ? null : false,
    tags: id % 5 === 0 ? [] : [{ k: "a,b]", v: [1, [2, { "}": "]" }]] }],
    trailing_backslash: "x\\",
  }))
}

const same = async (text: string) => {
  const progress: [number, number, string][] = []
  const value = await parseJSONSliced(text, (done, total, unit) => progress.push([done, total, unit]))
  expect(JSON.stringify(value)).toBe(JSON.stringify(JSON.parse(text)))
  expect(value).toEqual(JSON.parse(text))
  return progress
}

it("gives JSON.parse's value for a large answer, in pieces, with row counts as it goes", async () => {
  const text = JSON.stringify({ case_id: "c", transactions: rows(12000), total: 12000, meta: { a: [1, 2] }, more: rows(8000) })
  expect(text.length).toBeGreaterThan(SLICED_MINIMUM)
  const progress = await same(text)
  const counted = progress.filter(([, , unit]) => unit === "rows")
  expect(counted.at(-1)).toEqual([20000, 20000, "rows"])
  // Never backwards.
  for (let index = 1; index < counted.length; index += 1) expect(counted[index][0]).toBeGreaterThanOrEqual(counted[index - 1][0])
})

it("handles an answer that is one large array, and whitespace between parts", async () => {
  await same(JSON.stringify(rows(15000)))
  await same(JSON.stringify({ transactions: rows(15000), x: 1 }, null, 2))
  await same(` \n${JSON.stringify({ transactions: rows(15000) })}\n `)
})

it("throws JSON.parse's own error for invalid text, and matches it on repeated or __proto__ members", async () => {
  const good = JSON.stringify({ transactions: rows(15000) })
  const broken = [
    good.replace(/\}\]\}$/, "},]}"), // trailing comma
    good.slice(0, -10), // cut short
    good.replace('"id":5,', '"id":5,,'), // double comma inside a row
    good + "x", // text after the end
    good.replace('[{"id":0', '[,{"id":0'), // leading comma
  ]
  for (const text of broken) {
    expect(() => JSON.parse(text)).toThrow(SyntaxError)
    await expect(parseJSONSliced(text)).rejects.toThrow(SyntaxError)
  }
  const big = JSON.stringify(rows(15000))
  await same(`{"transactions":${big},"transactions":[1]}`)
  await same(`{"__proto__":${big},"x":1}`)
  const viaProto = (await parseJSONSliced<Record<string, unknown>>(`{"__proto__":${big}}`))
  expect(Object.getPrototypeOf(viaProto)).toBe(Object.prototype)
})

it("leaves small answers to one JSON.parse", async () => {
  const progress = await same(JSON.stringify({ transactions: rows(10) }))
  expect(progress).toEqual([])
})
