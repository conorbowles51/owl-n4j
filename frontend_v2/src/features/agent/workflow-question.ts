/** The named starting question of a guided workflow and its {person}, {other} and {date} slots. */
export const SLOTS: Record<string, string> = {
  person: "Person",
  other: "Other person",
  date: "Date",
}

/** The {person}, {other} and {date} slots a starting question asks for, in order. */
export function workflowSlots(question: string): string[] {
  const found: string[] = []
  for (const match of question.matchAll(/\{(person|other|date)\}/g)) {
    if (!found.includes(match[1])) found.push(match[1])
  }
  return found
}

export function fillWorkflowQuestion(question: string, values: Record<string, string>): string {
  return question.replace(/\{(person|other|date)\}/g, (_, key: string) => values[key]?.trim() || `[${SLOTS[key]}]`)
}
