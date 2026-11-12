/** Arithmetic only: no eval, property access, functions, assignments, or ambient JavaScript objects. */
export function evaluateScenario(expression: string, values: ReadonlyMap<string, number>): number {
  if (expression.length > 1000) throw new Error("This calculation is too long.")
  const tokens: string[] = []
  let offset = 0
  while (offset < expression.length) {
    const match = /^(?:\s+|(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?|[A-Za-z_][A-Za-z_0-9]*|[()+*/-])/i.exec(expression.slice(offset))
    if (!match) throw new Error("Use numbers, input names and arithmetic operators only.")
    offset += match[0].length
    if (match[0].trim()) tokens.push(match[0])
  }
  let position = 0
  let depth = 0
  const atom = (): number => {
    if (++depth > 64) throw new Error("The calculation is too deeply nested.")
    const token = tokens[position++]
    let value: number
    if (token === "+" || token === "-") value = atom() * (token === "-" ? -1 : 1)
    else if (token === "(") {
      value = sum()
      if (tokens[position++] !== ")") throw new Error("A closing parenthesis is missing.")
    } else if (token && /^(?:\d|\.)/.test(token)) value = Number(token)
    else if (token && values.has(token)) value = values.get(token)!
    else throw new Error(`Unknown input: ${token || "empty calculation"}.`)
    depth--
    return value
  }
  const product = (): number => {
    let value = atom()
    while (tokens[position] === "*" || tokens[position] === "/") {
      const op = tokens[position++]
      const other = atom()
      if (op === "/" && other === 0) throw new Error("Cannot divide by zero.")
      value = op === "*" ? value * other : value / other
    }
    return value
  }
  const sum = (): number => {
    let value = product()
    while (tokens[position] === "+" || tokens[position] === "-") {
      const op = tokens[position++]
      const other = product()
      value = op === "+" ? value + other : value - other
    }
    return value
  }
  const value = sum()
  if (position !== tokens.length || !Number.isFinite(value)) throw new Error("The calculation does not produce a finite number.")
  return value
}
