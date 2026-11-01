/**
 * JSON.parse for a large answer in pieces, giving the browser back between pieces so a loading panel keeps
 * redrawing (one 61 MB JSON.parse blocks the page's only thread for 0.5-1.4 s, measured on d5b330d1's ledger).
 *
 * How: one pass finds the elements of every large array that is the whole answer or a direct member of the
 * top-level object; everything else is parsed by JSON.parse with those arrays left empty, and each array's
 * elements are parsed by JSON.parse in batches of about BATCH_CHARS characters. The value is the one JSON.parse
 * gives for the whole text: the same parser reads every character. Whenever the text is not the plain shape this
 * pass understands (a trailing comma, a repeated or "__proto__" member, anything unexpected), or a piece fails to
 * parse, the whole text goes to JSON.parse, so invalid JSON throws JSON.parse's own error.
 */

export type UnpackProgress = (done: number, total: number, unit: "characters" | "rows") => void

/** Below this length one JSON.parse is quick enough (well under 50 ms). */
export const SLICED_MINIMUM = 2_000_000
const ARRAY_MINIMUM = 1_000_000
const BATCH_CHARS = 1_000_000
const BUDGET_MS = 25

const clock = () => (typeof performance !== "undefined" ? performance.now() : Date.now())

/** Back to the browser for one turn (a message task lets timers, input and drawing run first). */
export function yieldToBrowser(): Promise<void> {
  return new Promise((resolve) => {
    if (typeof MessageChannel !== "undefined") {
      const channel = new MessageChannel()
      channel.port1.onmessage = () => {
        channel.port1.close()
        resolve()
      }
      channel.port2.postMessage(null)
    } else setTimeout(resolve, 0)
  })
}

class Unexpected extends Error {}

const isSpace = (code: number) => code === 32 || code === 10 || code === 13 || code === 9

function skipSpace(text: string, at: number): number {
  while (at < text.length && isSpace(text.charCodeAt(at))) at += 1
  return at
}

/** Index just past the string starting at `at` (an opening quote). */
function stringEnd(text: string, at: number): number {
  let from = at + 1
  for (;;) {
    const quote = text.indexOf('"', from)
    if (quote < 0) throw new Unexpected()
    let slashes = 0
    for (let back = quote - 1; text.charCodeAt(back) === 92; back -= 1) slashes += 1
    if (slashes % 2 === 0) return quote + 1
    from = quote + 1
  }
}

/** Index just past the value starting at `at` (no leading space). JSON.parse checks it; this only finds its end. */
function valueEnd(text: string, at: number): number {
  const first = text.charCodeAt(at)
  if (first === 34) return stringEnd(text, at)
  if (first === 123 || first === 91) {
    // Jump from one quote or bracket to the next (a native search), skipping strings whole.
    let depth = 0
    const marks = /["{}[\]]/g
    marks.lastIndex = at
    for (;;) {
      const found = marks.exec(text)
      if (!found) throw new Unexpected()
      const index = found.index
      const code = text.charCodeAt(index)
      if (code === 34) marks.lastIndex = stringEnd(text, index)
      else if (code === 123 || code === 91) depth += 1
      else {
        depth -= 1
        if (depth === 0) return index + 1
      }
    }
  }
  let index = at
  while (index < text.length) {
    const code = text.charCodeAt(index)
    if (code === 44 || code === 93 || code === 125 || isSpace(code)) break
    index += 1
  }
  if (index === at) throw new Unexpected()
  return index
}

interface ArraySpan {
  /** Index of "[" and just past "]". */
  open: number
  close: number
  /** [start, end) of each element. */
  starts: number[]
  ends: number[]
  /** The top-level member holding it; null when the array is the whole answer. */
  key: string | null
}

/** Finds the elements of the array opening at `open`, giving the browser a turn every BUDGET_MS. */
async function scanArray(
  text: string,
  open: number,
  key: string | null,
  progress: UnpackProgress | undefined,
  budget: { since: number }
): Promise<ArraySpan> {
  const starts: number[] = []
  const ends: number[] = []
  let at = skipSpace(text, open + 1)
  if (text.charCodeAt(at) === 93) return { open, close: at + 1, starts, ends, key }
  for (;;) {
    const end = valueEnd(text, at)
    starts.push(at)
    ends.push(end)
    at = skipSpace(text, end)
    const code = text.charCodeAt(at)
    if (code === 93) return { open, close: at + 1, starts, ends, key }
    if (code !== 44) throw new Unexpected()
    at = skipSpace(text, at + 1)
    if (at >= text.length || text.charCodeAt(at) === 93) throw new Unexpected()
    if ((starts.length & 255) === 0 && clock() - budget.since > BUDGET_MS) {
      progress?.(at, text.length, "characters")
      await yieldToBrowser()
      budget.since = clock()
    }
  }
}

async function findArrays(text: string, progress: UnpackProgress | undefined, budget: { since: number }): Promise<ArraySpan[]> {
  let at = skipSpace(text, 0)
  const first = text.charCodeAt(at)
  if (first === 91) {
    const span = await scanArray(text, at, null, progress, budget)
    if (skipSpace(text, span.close) !== text.length) throw new Unexpected()
    return [span]
  }
  if (first !== 123) throw new Unexpected()
  const spans: ArraySpan[] = []
  const keys = new Set<string>()
  at = skipSpace(text, at + 1)
  if (text.charCodeAt(at) === 125) return spans
  for (;;) {
    if (text.charCodeAt(at) !== 34) throw new Unexpected()
    const keyEnd = stringEnd(text, at)
    const key = JSON.parse(text.slice(at, keyEnd)) as string
    if (keys.has(key) || key === "__proto__") throw new Unexpected()
    keys.add(key)
    at = skipSpace(text, keyEnd)
    if (text.charCodeAt(at) !== 58) throw new Unexpected()
    at = skipSpace(text, at + 1)
    let end: number
    if (text.charCodeAt(at) === 91) {
      const span = await scanArray(text, at, key, progress, budget)
      end = span.close
      if (span.close - span.open >= ARRAY_MINIMUM) spans.push(span)
    } else end = valueEnd(text, at)
    at = skipSpace(text, end)
    const code = text.charCodeAt(at)
    if (code === 125) {
      if (skipSpace(text, at + 1) !== text.length) throw new Unexpected()
      return spans
    }
    if (code !== 44) throw new Unexpected()
    at = skipSpace(text, at + 1)
  }
}

async function parseInPieces(text: string, progress: UnpackProgress | undefined): Promise<unknown> {
  const budget = { since: clock() }
  const spans = await findArrays(text, progress, budget)
  if (!spans.length) return JSON.parse(text)
  // Everything outside the large arrays, with each left empty.
  const pieces: string[] = []
  let from = 0
  for (const span of spans) {
    pieces.push(text.slice(from, span.open), "[]")
    from = span.close
  }
  pieces.push(text.slice(from))
  const result = JSON.parse(pieces.join("")) as unknown
  const rows = spans.reduce((sum, span) => sum + span.starts.length, 0)
  let done = 0
  const arrays: unknown[][] = []
  for (const span of spans) {
    const values: unknown[] = []
    let index = 0
    while (index < span.starts.length) {
      let last = index
      while (last + 1 < span.starts.length && span.ends[last + 1] - span.starts[index] <= BATCH_CHARS) last += 1
      const batch = JSON.parse(`[${text.slice(span.starts[index], span.ends[last])}]`) as unknown[]
      if (batch.length !== last - index + 1) throw new Unexpected()
      for (const value of batch) values.push(value)
      done += batch.length
      index = last + 1
      if (clock() - budget.since > BUDGET_MS) {
        progress?.(done, rows, "rows")
        await yieldToBrowser()
        budget.since = clock()
      }
    }
    arrays.push(values)
  }
  progress?.(rows, rows, "rows")
  if (spans.length === 1 && spans[0].key === null) return arrays[0]
  const target = result as Record<string, unknown>
  spans.forEach((span, position) => {
    target[span.key as string] = arrays[position]
  })
  return result
}

/** The value JSON.parse(text) gives, parsed in pieces when the text is large. */
export async function parseJSONSliced<T>(text: string, progress?: UnpackProgress): Promise<T> {
  if (text.length < SLICED_MINIMUM) return JSON.parse(text) as T
  try {
    return (await parseInPieces(text, progress)) as T
  } catch {
    // Not the plain shape, or not valid JSON: the whole text to JSON.parse (its value, or its own error).
    return JSON.parse(text) as T
  }
}
