import { expect, it } from "vitest"
import { markedWords } from "./marked-words"

it("says what the Significant layer holds, relationships beside entities (GR-01)", () => {
  expect(markedWords(3, 0)).toBe("3 marked entities")
  expect(markedWords(1, 1)).toBe("1 marked entity, 1 relationship")
  expect(markedWords(0, 2)).toBe("0 marked entities, 2 relationships")
})
