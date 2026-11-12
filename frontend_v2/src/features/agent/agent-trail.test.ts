import { expect, it } from "vitest"

import { trailNewestFirst, type InvestigationTrailStep } from "./agent-trail"
import type { AgentSteeringEntry } from "./types"

const step = (n: number): InvestigationTrailStep => ({ id: `s${n}`, title: `Step ${n}`, status: "success" })
const entry = (id: string, at: number | null): AgentSteeringEntry => ({
  id, kind: "switch", group: "phones", on: false, title: `You switched off Phones (${id})`,
  result: "The agent will not use these tools for the rest of this answer.", step: at,
  applies_from: at == null ? null : at + 1,
})

it("lists the trail newest first with each switch after the step it was taken at (tool steering C)", () => {
  const out = trailNewestFirst([step(1), step(2), step(3)], [entry("a", 1), entry("b", null)])
  expect(out.map((s) => s.id)).toEqual(["steer_b", "s3", "s2", "steer_a", "s1"])
})

it("keeps the old order of tool steps reversed when nothing was switched", () => {
  expect(trailNewestFirst([step(1), step(2)], []).map((s) => s.id)).toEqual(["s2", "s1"])
})
