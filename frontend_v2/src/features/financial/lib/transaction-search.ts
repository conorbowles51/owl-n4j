import { currencyMinorUnits } from "./ledger-format"
import type { LedgerTransaction } from "../api"
import { correctionMoney } from "./correction-contract"

type Node =
  | { term: string; field?: string }
  | { op: "NOT"; value: Node }
  | { op: "AND" | "OR"; left: Node; right: Node }
const fields: Record<string, keyof LedgerTransaction> = {
  from: "from_name",
  to: "to_name",
  category: "category",
  description: "description",
  reference: "bank_reference",
  date: "ordering_date",
  currency: "currency",
  account: "account_label",
}
export function parseTransactionSearch(query: string): Node | null {
  if (!query.trim()) return null
  const tokens =
    query.match(/(?:[a-zA-Z]+:)?"(?:\\.|[^"\\])*"|\(|\)|[^\s()"]+/g) ?? []
  if (tokens.join("").replace(/\s/g, "") !== query.replace(/\s/g, ""))
    throw Error("Close each quoted phrase before searching.")
  let index = 0
  const primary = (): Node => {
    const token = tokens[index++]
    if (!token || ["AND", "OR", ")"].includes(token))
      throw Error("Enter a term after each operator.")
    if (token === "NOT") return { op: "NOT", value: primary() }
    if (token === "(") {
      const value = or()
      if (tokens[index++] !== ")")
        throw Error("Close each opening parenthesis.")
      return value
    }
    const match = token.match(/^([a-zA-Z]+):(.*)$/)
    const field = match?.[1].toLowerCase()
    if (field && !(field in fields) && field !== "amount")
      throw Error(`Unknown search field: ${field}.`)
    let term = match ? match[2] : token
    if (!term) throw Error("Enter a value after the field name.")
    if (term.startsWith('"')) term = term.slice(1, -1).replace(/\\(.)/g, "$1")
    if (!term.trim()) throw Error("Enter text inside quoted phrases.")
    return { term: term.toLowerCase(), ...(field ? { field } : {}) }
  }
  const and = (): Node => {
    let value = primary()
    while (index < tokens.length && !["OR", ")"].includes(tokens[index])) {
      if (tokens[index] === "AND") index++
      value = { op: "AND", left: value, right: primary() }
    }
    return value
  }
  const or = (): Node => {
    let value = and()
    while (tokens[index] === "OR") {
      index++
      value = { op: "OR", left: value, right: and() }
    }
    return value
  }
  const result = or()
  if (index !== tokens.length)
    throw Error("Remove the unmatched closing parenthesis.")
  return result
}
export function transactionSearch(query: string, mode: string = "text") {
  let tree: Node | null
  try {
    tree =
      mode === "boolean"
        ? parseTransactionSearch(query)
        : query.trim()
          ? { term: query.trim().toLowerCase() }
          : null
  } catch (error) {
    return { error: (error as Error).message, matches: () => false }
  }
  if (!tree) return { error: null, matches: () => true }
  const matches = (row: LedgerTransaction) => {
    const values: Record<string, string> = Object.fromEntries(
      Object.entries(fields).map(([name, field]) => [
        name,
        String(row[field] ?? ""),
      ])
    )
    values.category ||= "Uncategorized"
    values.amount = correctionMoney(
      String(row.amount_minor),
      row.currency
    ).split(" ")[0]
    const all = [
      ...Object.values(values),
      row.ref_id,
      row.key,
      row.counterparty_raw,
      row.account_holder,
      row.account_id,
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase()
    const evaluate = (node: Node): boolean =>
      "term" in node
        ? (node.field ? values[node.field].toLowerCase() : all).includes(
            node.term
          )
        : node.op === "NOT"
          ? !evaluate(node.value)
          : node.op === "AND"
            ? evaluate(node.left) && evaluate(node.right)
            : evaluate(node.left) || evaluate(node.right)
    return !tree || evaluate(tree)
  }
  return { error: null, matches }
}

export function compareDisplayedAmounts(
  a: LedgerTransaction,
  b: LedgerTransaction
) {
  const leftScale = currencyMinorUnits(a.currency) ?? 0
  const rightScale = currencyMinorUnits(b.currency) ?? 0
  const left = BigInt(a.amount_minor) * 10n ** BigInt(rightScale)
  const right = BigInt(b.amount_minor) * 10n ** BigInt(leftScale)
  return left < right ? -1 : left > right ? 1 : 0
}
