import { z } from "zod"
import type { AmountCorrection, BulkCorrectionResult } from "../api"

export interface FileCorrection {
  node_key: string
  new_amount: number
  correction_reason: string
  line: number
}

export function verifyBulkCorrectionResponse(
  raw: unknown,
  requested: AmountCorrection[]
): BulkCorrectionResult {
  const row = z.discriminatedUnion("status", [
    z.object({
      key: z.string(),
      status: z.literal("corrected"),
      old_amount: z.number().nullable().optional(),
      old_raw_amount: z.string().nullable().optional(),
      new_amount: z.number(),
    }),
    z.object({
      key: z.string(),
      status: z.literal("error"),
      reason: z.string().min(1),
    }),
  ])
  const value = z
    .object({
      success: z.boolean(),
      corrected: z.number().int().nonnegative(),
      errors: z.number().int().nonnegative(),
      total: z.number().int().min(1).max(1000),
      results: z.array(row).max(1000),
    })
    .parse(raw)
  const byKey = new Map(requested.map((item) => [item.node_key, item]))
  const corrected = value.results.filter(
    (item) => item.status === "corrected"
  ).length
  if (
    value.total !== requested.length ||
    value.results.length !== requested.length ||
    new Set(value.results.map((item) => item.key)).size !== requested.length ||
    value.corrected !== corrected ||
    value.errors !== requested.length - corrected ||
    value.success !== (corrected === requested.length) ||
    value.results.some((item) => {
      const request = byKey.get(item.key)
      return (
        !request ||
        (item.status === "corrected" &&
          (item.new_amount !== request.new_amount ||
            (request.expected_amount !== undefined &&
              item.old_amount !== request.expected_amount) ||
            (request.expected_raw_amount !== undefined &&
              (item.old_amount !== null ||
                item.old_raw_amount !== request.expected_raw_amount))))
      )
    })
  )
    throw Error(
      "The response does not confirm these corrections. Check the current records before retrying."
    )
  return value
}

// Keep quoted delimiters, doubled quotes and multiline explanations intact.
function records(text: string, delimiter: string) {
  const result: { cells: string[]; line: number }[] = []
  let cells: string[] = [],
    cell = "",
    quoted = false,
    closed = false,
    line = 1,
    start = 1
  const endCell = () => {
    cells.push(cell.trim())
    cell = ""
    closed = false
  }
  const endRow = () => {
    endCell()
    if (cells.some(Boolean)) result.push({ cells, line: start })
    cells = []
    start = line + 1
  }
  text = text.replace(/^\uFEFF/, "")
  for (let i = 0; i < text.length; i++) {
    const char = text[i]
    if (quoted) {
      if (char === '"') {
        if (text[i + 1] === '"') {
          cell += '"'
          i++
        } else {
          quoted = false
          closed = true
        }
      } else {
        cell += char
        if (char === "\n") line++
      }
    } else if (char === delimiter) endCell()
    else if (char === "\n" || char === "\r") {
      if (char === "\r" && text[i + 1] === "\n") i++
      endRow()
      line++
    } else if (char === '"' && !cell.trim() && !closed) {
      cell = ""
      quoted = true
    } else if (char === '"' || (closed && char.trim()))
      throw Error(`Line ${line}: check the quotation marks around this field.`)
    else cell += char
  }
  if (quoted)
    throw Error(
      `Line ${start}: a quoted field is missing its closing quotation mark.`
    )
  endRow()
  return result
}

function decimalValue(value: string) {
  // Compare decimal digits before/after Number conversion to reject rounding.
  const canonical = (input: string) => {
    const [mantissa, exponent = "0"] = input.toLowerCase().split("e")
    const negative = mantissa.startsWith("-")
    const [whole, fraction = ""] = mantissa.replace(/^[+-]/, "").split(".")
    let digits = (whole + fraction).replace(/^0+/, "") || "0"
    let scale = fraction.length - Number(exponent)
    while (digits.endsWith("0") && digits !== "0") {
      digits = digits.slice(0, -1)
      scale--
    }
    return `${negative && digits !== "0" ? "-" : ""}${digits}:${scale}`
  }
  if (!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(value)) return null
  const number = Number(value)
  if ((value.split(".")[1] ?? "").replace(/0+$/, "").length > 2) return null
  return Number.isFinite(number) &&
    number !== 0 &&
    canonical(value) === canonical(String(number))
    ? number
    : null
}

export function parseCorrectionFile(
  text: string,
  filename: string
): FileCorrection[] {
  if (!/\.(csv|tsv|txt)$/i.test(filename))
    throw Error(
      "Choose a CSV or TSV file. Save an Excel workbook as CSV first."
    )
  if (text.length > 2 * 1024 * 1024)
    throw Error("Choose a correction file smaller than 2 MB.")
  const first = text.split(/\r?\n/, 1)[0]
  const delimiter =
    /\.tsv$/i.test(filename) || (first.includes("\t") && !first.includes(","))
      ? "\t"
      : ","
  const rows = records(text, delimiter)
  if (rows.length < 2)
    throw Error("Include the column headings and at least one correction.")
  if (rows.length > 1001)
    throw Error("A correction file can contain up to 1,000 records.")
  const headers = rows[0].cells.map((name) =>
    name.toLowerCase().replace(/[^a-z]/g, "")
  )
  const column = (aliases: string[], name: string) => {
    const positions = headers.flatMap((header, index) =>
      aliases.includes(header) ? [index] : []
    )
    if (positions.length !== 1)
      throw Error(`Include exactly one ${name} column.`)
    return positions[0]
  }
  const key = column(["key", "id", "nodekey", "transactionid"], "key"),
    amount = column(["amount", "newamount"], "amount"),
    reason = column(["reason", "correctionreason"], "reason")
  const seen = new Set<string>()
  return rows.slice(1).map(({ cells, line }) => {
    if (cells.length !== headers.length)
      throw Error(
        `Line ${line}: the number of fields does not match the headings.`
      )
    const node_key = cells[key],
      new_amount = decimalValue(cells[amount]),
      correction_reason = cells[reason]
    if (!node_key) throw Error(`Line ${line}: the record key is missing.`)
    if (seen.has(node_key))
      throw Error(`Line ${line}: record ${node_key} appears more than once.`)
    seen.add(node_key)
    if (new_amount === null)
      throw Error(
        `Line ${line}: enter a non-zero decimal amount with at most two decimal places, without currency symbols or thousands separators. The amount must be saved without rounding.`
      )
    if (!correction_reason || correction_reason.length > 4000)
      throw Error(`Line ${line}: enter a reason of 1 to 4,000 characters.`)
    return { node_key, new_amount, correction_reason, line }
  })
}
