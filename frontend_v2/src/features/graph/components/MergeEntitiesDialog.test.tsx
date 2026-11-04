import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, expect, it, vi } from "vitest"
import type { GraphNode } from "@/types/graph.types"
import { graphAPI } from "../api"
import { MergeEntitiesDialog } from "./MergeEntitiesDialog"

const node = (i: number, type = "Person") => ({ key: `k${i}`, id: `k${i}`, label: `Orla Test ${i}`, type }) as unknown as GraphNode

const open = (entities: GraphNode[]) => {
  const onStartTracking = vi.fn()
  render(
    <MergeEntitiesDialog open onOpenChange={() => {}} entities={entities} caseId="case-1" activeJob={null}
      onStartTracking={onStartTracking} onClearJob={() => {}} />
  )
  return onStartTracking
}

beforeEach(() => {
  vi.restoreAllMocks()
})

it("merges 8 selected duplicates in one request with the chosen name and type (FEAT-004)", async () => {
  const merge = vi.spyOn(graphAPI, "mergeEntities").mockResolvedValue({ job_id: "e1", merge_job_id: "m1" })
  const entities = Array.from({ length: 8 }, (_, i) => node(i, i === 7 ? "Organization" : "Person"))
  const onStartTracking = open(entities)
  fireEvent.click(screen.getByRole("button", { name: "Use Orla Test 0 as preferred name" }))
  fireEvent.change(screen.getByLabelText("Type of the merged entity"), { target: { value: "Person" } })
  fireEvent.click(screen.getByRole("button", { name: /Merge 8 with AI/ }))
  await waitFor(() => expect(merge).toHaveBeenCalledTimes(1))
  expect(merge).toHaveBeenCalledWith("case-1", entities.map((e) => e.key), "Orla Test 0", "Person")
  expect(onStartTracking).toHaveBeenCalledWith("e1", "m1", entities.map((e) => e.key))
  expect(screen.queryByRole("status")).toBeNull()
})

it("over 25 selected: says how many are left out and merges the first 25", async () => {
  const merge = vi.spyOn(graphAPI, "mergeEntities").mockResolvedValue({ job_id: "e1", merge_job_id: "m1" })
  const entities = Array.from({ length: 31 }, (_, i) => node(i))
  open(entities)
  expect(screen.getByRole("status").textContent).toContain("6 more are left out of this merge")
  fireEvent.click(screen.getByRole("button", { name: /Merge 25 with AI/ }))
  await waitFor(() => expect(merge).toHaveBeenCalledTimes(1))
  expect(merge.mock.calls[0][1]).toEqual(entities.slice(0, 25).map((e) => e.key))
  expect(merge.mock.calls[0][3]).toBeUndefined()
})

it("keeps the dialog on screen with 25 entities: the body and the entity list scroll, the merge button stays (FEAT-004)", () => {
  open(Array.from({ length: 25 }, (_, i) => node(i)))
  expect(screen.getByRole("dialog").className).toContain("max-h-[calc(100dvh-2rem)]")
  expect(screen.getByTestId("merge-body").className).toContain("overflow-y-auto")
  expect(screen.getByTestId("merge-entities").className).toContain("overflow-y-auto")
})
