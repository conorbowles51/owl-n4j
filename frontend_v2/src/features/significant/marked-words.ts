/** "3 marked entities, 2 relationships": what the Significant layer holds. */
export function markedWords(entities: number, relationships: number): string {
  const e = `${entities.toLocaleString()} marked ${entities === 1 ? "entity" : "entities"}`
  return relationships > 0
    ? `${e}, ${relationships.toLocaleString()} ${relationships === 1 ? "relationship" : "relationships"}`
    : e
}
