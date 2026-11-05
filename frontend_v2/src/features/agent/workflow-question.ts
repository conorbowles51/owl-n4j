/** The named starting question of a guided workflow and its {person}, {other}, {date} and {theory} slots. */
export const SLOTS: Record<string, string> = {
  person: "Person",
  other: "Other person",
  date: "Date",
  theory: "Theory",
}

/** The {person}, {other}, {date} and {theory} slots a starting question asks for, in order. */
export function workflowSlots(question: string): string[] {
  const found: string[] = []
  for (const match of question.matchAll(/\{(person|other|date|theory)\}/g)) {
    if (!found.includes(match[1])) found.push(match[1])
  }
  return found
}

export function fillWorkflowQuestion(question: string, values: Record<string, string>): string {
  return question.replace(/\{(person|other|date|theory)\}/g, (_, key: string) => values[key]?.trim() || `[${SLOTS[key]}]`)
}
