import { beforeEach, describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen } from "@testing-library/react"
import { corroborateAPI, type Grouped } from "./api"
import { againstOthers, eachRuns } from "./group-runs"
import { GroupPicker } from "./GroupPicker"

const g = (key: string, count: number, people: string[]) => ({ key, label: key, count, people, members: [{ type: "phone_record", id: key }] })
const grouped: Grouped = {
  by: "day", group_count: 3, clipped: 0, in_several_groups: 0, unread: 0,
  groups: [g("2026-05-03", 5, ["person:a"]), g("2026-05-04", 3, ["person:b"]), g("2026-05-05", 1, [])],
  left_out: [{ count: 2, why: "has no date" }], left_out_total: 2,
}
beforeEach(() => vi.restoreAllMocks())

describe("Group a selection", () => {
  it("compares a group with the people of every other group, and runs only groups that name someone", () => {
    expect(againstOthers(grouped.groups, grouped.groups[0])).toEqual(["person:b"])
    const e = eachRuns(grouped.groups)
    expect(e.runs.map((r) => r.key)).toEqual(["2026-05-03", "2026-05-04"])
    expect(e.withoutPeople).toBe(1)
  })
  it("shows whole counts per group, says what is in no group, and hands a group or all groups on", async () => {
    vi.spyOn(corroborateAPI, "group").mockResolvedValue(grouped)
    const onGroup = vi.fn(), onEach = vi.fn()
    render(<GroupPicker caseId="c1" members={[{ type: "phone_record", id: "x" }]} busy={false} onGroup={onGroup} onEach={onEach} />)
    fireEvent.change(screen.getByLabelText("Group by"), { target: { value: "day" } })
    await screen.findByText(/2 items are in no group: each has no date/)
    expect(screen.getByText(/5 items/)).toBeTruthy()
    expect((screen.getAllByRole("button", { name: "Ask about this group" })[2] as HTMLButtonElement).disabled).toBe(true)
    fireEvent.click(screen.getAllByRole("button", { name: "Ask about this group" })[0])
    expect(onGroup.mock.calls[0][0].key).toBe("2026-05-03")
    fireEvent.click(screen.getByRole("button", { name: /Each group against the others \(2 runs\)/ }))
    expect(onEach.mock.calls[0][0]).toHaveLength(2)
  })
})
