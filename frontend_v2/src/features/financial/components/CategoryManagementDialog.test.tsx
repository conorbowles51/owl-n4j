import { act, fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, expect, it, vi } from "vitest"
import { useFinancialDraftStore } from "../stores/financial-drafts"
import { CategoryManagementDialog } from "./CategoryManagementDialog"

beforeEach(() => useFinancialDraftStore.setState({ drafts: {} }))
function show(save = vi.fn().mockResolvedValue({}), caseId = "case-a") {
  const close = vi.fn()
  const view = render(
    <CategoryManagementDialog
      caseId={caseId}
      open
      onOpenChange={close}
      categories={[]}
      onCreateCategory={save}
    />
  )
  return { ...view, save, close }
}
function enter() {
  fireEvent.change(screen.getByLabelText("Category name"), {
    target: { value: "Review, priority" },
  })
  fireEvent.click(
    screen.getByRole("button", { name: "Category colour #5571c8" })
  )
}
it("retains an unsuccessful category name and colour through reopening while isolating cases", async () => {
  const first = show(
    vi.fn().mockRejectedValue(new Error("Request interrupted"))
  )
  enter()
  fireEvent.click(screen.getByRole("button", { name: "Add Category" }))
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Request interrupted"
  )
  first.unmount()
  const other = show(undefined, "case-b")
  expect(screen.getByLabelText("Category name")).toHaveValue("")
  other.unmount()
  show()
  expect(screen.getByLabelText("Category name")).toHaveValue("Review, priority")
  expect(
    screen.getByRole("button", { name: "Category colour #5571c8" })
  ).toHaveAttribute("aria-pressed", "true")
})
it("blocks repeated Enter and close while saving, then clears only the confirmed draft", async () => {
  let resolve!: () => void
  const save = vi.fn(
    () =>
      new Promise<void>((done) => {
        resolve = done
      })
  )
  const view = show(save)
  enter()
  fireEvent.keyDown(screen.getByLabelText("Category name"), { key: "Enter" })
  fireEvent.keyDown(screen.getByLabelText("Category name"), { key: "Enter" })
  for (const button of screen.getAllByRole("button", { name: "Close" }))
    fireEvent.click(button)
  expect(view.close).not.toHaveBeenCalled()
  expect(save).toHaveBeenCalledExactlyOnceWith("Review, priority", "#5571c8")
  expect(screen.getByLabelText("Category name")).toHaveValue("Review, priority")
  await act(async () => resolve())
  expect(screen.getByRole("status")).toHaveTextContent(
    'Category "Review, priority" saved'
  )
  expect(screen.getByLabelText("Category name")).toHaveValue("")
  expect(Object.keys(useFinancialDraftStore.getState().drafts)).toHaveLength(0)
})
it("directs the user to an existing category instead of recreating it", () => {
  const save = vi.fn()
  render(
    <CategoryManagementDialog
      caseId="case-a"
      open
      onOpenChange={vi.fn()}
      categories={[{ name: "Existing", color: "#b41624" }]}
      onCreateCategory={save}
    />
  )
  fireEvent.change(screen.getByLabelText("Category name"), {
    target: { value: " existing " },
  })
  expect(screen.getByRole("status")).toHaveTextContent("already exists")
  expect(screen.getByRole("button", { name: "Add Category" })).toBeDisabled()
  fireEvent.keyDown(screen.getByLabelText("Category name"), { key: "Enter" })
  expect(save).not.toHaveBeenCalled()
})
