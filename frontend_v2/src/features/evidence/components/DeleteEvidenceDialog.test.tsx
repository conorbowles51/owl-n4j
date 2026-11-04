import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { DeleteEvidenceDialog } from "./DeleteEvidenceDialog"
import { DeleteFolderDialog } from "./DeleteFolderDialog"

describe("Evidence delete dialogs follow the Deleted items setting", () => {
  it("switched off (live): permanent, as before, with no Deleted items or restore wording", () => {
    render(<DeleteEvidenceDialog open onOpenChange={() => {}} fileCount={2} onConfirm={() => {}} />)
    expect(screen.getByText(/permanently delete 2 files/)).toBeTruthy()
    expect(screen.getByRole("button", { name: "Delete" })).toBeTruthy()
    expect(document.body.textContent ?? "").not.toMatch(/Deleted items|restore|30 days/i)
  })

  it("switched on: moved to Deleted items for 30 days", () => {
    render(<DeleteEvidenceDialog open onOpenChange={() => {}} fileCount={1} onConfirm={() => {}} deletedItems />)
    expect(screen.getByRole("button", { name: "Move to Deleted items" })).toBeTruthy()
    expect(document.body.textContent ?? "").toMatch(/for 30 days/)
  })

  it("a folder delete switched off says the files go for good and the graph stays, as before", () => {
    render(
      <DeleteFolderDialog open onOpenChange={() => {}} folderName="Bank" fileCount={3} onConfirm={() => {}} />
    )
    expect(screen.getByText(/3 files will be permanently deleted/)).toBeTruthy()
    expect(document.body.textContent ?? "").not.toMatch(/Deleted items|restore|30 days/i)
  })
})
