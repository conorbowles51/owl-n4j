import type { GraphNode } from "@/types/graph.types"

export type SearchQuery =
  | { type: "term"; value: string; quoted?: boolean }
  | { type: "not"; operand: SearchQuery }
  | { type: "and"; left: SearchQuery; right: SearchQuery }
  | { type: "or"; left: SearchQuery; right: SearchQuery }

type Token =
  | { type: "term"; value: string; quoted?: boolean }
  | { type: "operator"; value: "AND" | "OR" | "NOT" }

function tokenize(query: string): Token[] {
  const tokens: Token[] = []
  let current = ""
  let quote: "'" | '"' | null = null

  const pushCurrent = (quoted = false) => {
    const value = current.trim()
    current = ""
    if (!value) return
    const operator = value.toUpperCase()
    if (!quoted && (operator === "AND" || operator === "OR" || operator === "NOT")) {
      tokens.push({ type: "operator", value: operator })
    } else {
      tokens.push({ type: "term", value, quoted })
    }
  }

  for (let index = 0; index < query.length; index += 1) {
    const char = query[index]
    if (quote) {
      if (char === quote) {
        pushCurrent(true)
        quote = null
      } else {
        current += char
      }
      continue
    }
    if (char === "'" || char === '"') {
      pushCurrent()
      quote = char
    } else if (/\s/.test(char)) {
      pushCurrent()
    } else if (char === "-" && (index === 0 || /\s/.test(query[index - 1]))) {
      pushCurrent()
      tokens.push({ type: "operator", value: "NOT" })
    } else {
      current += char
    }
  }
  pushCurrent(Boolean(quote))
  return tokens
}

class Parser {
  private index = 0
  private readonly tokens: Token[]

  constructor(tokens: Token[]) {
    this.tokens = tokens
  }

  parse(): SearchQuery | null {
    return this.parseOr()
  }

  private parseOr(): SearchQuery | null {
    let left = this.parseAnd()
    while (this.peekOperator("OR")) {
      this.index += 1
      const right = this.parseAnd()
      if (left && right) left = { type: "or", left, right }
    }
    return left
  }

  private parseAnd(): SearchQuery | null {
    let left = this.parseUnary()
    while (this.index < this.tokens.length && !this.peekOperator("OR")) {
      if (this.peekOperator("AND")) this.index += 1
      const right = this.parseUnary()
      if (!right) continue
      left = left ? { type: "and", left, right } : right
    }
    return left
  }

  private parseUnary(): SearchQuery | null {
    if (this.peekOperator("NOT")) {
      this.index += 1
      const operand = this.parseUnary()
      return operand ? { type: "not", operand } : null
    }
    const token = this.tokens[this.index]
    if (!token) return null
    this.index += 1
    if (token.type === "operator") return null
    return { type: "term", value: token.value, quoted: token.quoted }
  }

  private peekOperator(value: "AND" | "OR" | "NOT") {
    const token = this.tokens[this.index]
    return token?.type === "operator" && token.value === value
  }
}

export function parseSearchQuery(query: string): SearchQuery | null {
  return new Parser(tokenize(query)).parse()
}

function primitiveValues(value: unknown): string[] {
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return [String(value)]
  }
  if (Array.isArray(value)) return value.flatMap(primitiveValues)
  return []
}

export function getNodeSearchText(node: GraphNode): string {
  return [
    node.label,
    node.key,
    ...node.aliases ?? [],
    node.type,
    node.summary ?? "",
    node.notes ?? "",
    ...Object.values(node.properties).flatMap(primitiveValues),
  ].join(" ").toLowerCase()
}

function wildcardPattern(term: string): RegExp {
  const escaped = term.replace(/[.+^${}()|[\]\\]/g, "\\$&")
  return new RegExp(escaped.replace(/\*/g, ".*").replace(/\?/g, "."), "i")
}

export function matchesSearchQuery(query: SearchQuery | null, node: GraphNode): boolean {
  if (!query) return true
  if (query.type === "not") return !matchesSearchQuery(query.operand, node)
  if (query.type === "and") {
    return matchesSearchQuery(query.left, node) && matchesSearchQuery(query.right, node)
  }
  if (query.type === "or") {
    return matchesSearchQuery(query.left, node) || matchesSearchQuery(query.right, node)
  }
  const text = getNodeSearchText(node)
  const term = query.value.toLowerCase()
  return term.includes("*") || term.includes("?")
    ? wildcardPattern(term).test(text)
    : text.includes(term)
}
