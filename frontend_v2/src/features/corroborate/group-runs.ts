import type { ItemGroup } from "./api"

/** At most this many groups are run in one "each against the others"; the screen says when it stopped there. */
export const MAX_EACH = 6

/** The people of every other group: who a group is compared against. */
export function againstOthers(groups: ItemGroup[], one: ItemGroup): string[] {
  const out: string[] = []
  for (const g of groups) {
    if (g.key === one.key) continue
    for (const p of g.people) if (!one.people.includes(p) && !out.includes(p)) out.push(p)
  }
  return out
}

/** The groups an "each against the others" runs: the biggest first, those with someone to compare with only. */
export function eachRuns(groups: ItemGroup[]): { runs: ItemGroup[]; skipped: number; withoutPeople: number } {
  const usable = groups.filter((g) => g.people.length > 0)
  const runs = usable.slice(0, MAX_EACH)
  return { runs, skipped: usable.length - runs.length, withoutPeople: groups.length - usable.length }
}
