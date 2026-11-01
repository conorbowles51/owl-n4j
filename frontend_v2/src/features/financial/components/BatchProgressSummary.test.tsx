import { render, screen, within } from "@testing-library/react"
import { expect, it, vi } from "vitest"
import { BatchProgressSummary } from "./BatchProgressSummary"
import { BatchReadyAction } from "./BatchReadyAction"
const summary = {
  total: 14,
  available: 7,
  blocked: 6,
  imported: 1,
  pending_import: 0,
  skipped: 0,
  possible_duplicates: 0,
  duplicate_ignored: 0,
  assigned: 0,
  other: 0,
  available_with_payments: 0,
  available_no_activity: 7,
  available_other: 0,
}
it("keeps PDF totals separate from whole-batch exclusive review statuses", () => {
  render(
    <BatchProgressSummary
      files={Array.from({ length: 11 }, () => ({ status: "checked" }))}
      summary={summary}
      available={0}
      imported={0}
      pending={0}
      skipped={0}
      duplicates={0}
      assigned={0}
    />
  )
  expect(screen.getByText("11 of 11 files read")).toBeVisible()
  expect(screen.getByText("14 prepared statement reviews")).toBeVisible()
  for (const [label, value] of [
    ["Ready to save", "7"],
    ["Needs review before saving", "6"],
    ["Saved to Financial", "1"],
  ])
    expect(
      within(screen.getByText(label).parentElement!).getByText(value)
    ).toBeVisible()
  expect(screen.getByText(/Review reasons below may overlap/)).toBeVisible()
})
const props = {
  available: 7,
  payments: 0,
  incomplete: 0,
  summary,
  filtered: true,
  canEdit: true,
  paused: false,
  pending: false,
  accepted: false,
  onConfirm: vi.fn(),
}
it("never describes unknown zero-row readiness as confirmed no activity", () => {
  render(
    <BatchReadyAction
      {...props}
      summary={{ ...summary, available_no_activity: 0, available_other: 7 }}
    />
  )
  expect(
    screen.getByRole("button", { name: "Save 7 statements to Financial" })
  ).toBeEnabled()
  expect(
    screen.getByText(/A zero payment count alone does not confirm no activity/)
  ).toBeVisible()
  expect(screen.queryByText(/are confirmed to contain no payments/)).toBeNull()
  expect(
    screen.getByText(/including statements outside the review filter/)
  ).toBeVisible()
})
it("names both payment import and all saved statements in a mixed ready batch", () => {
  render(
    <BatchReadyAction
      {...props}
      available={3}
      payments={12}
      summary={{
        ...summary,
        available: 3,
        available_with_payments: 2,
        available_no_activity: 1,
      }}
    />
  )
  expect(
    screen.getByRole("button", {
      name: "Import 12 transactions and save 3 statements",
    })
  ).toBeEnabled()
  expect(
    screen.getByText(/1 ready statement is confirmed to contain no payments/)
  ).toBeVisible()
})
it("explains a paused save without offering an enabled no-op", () => {
  render(<BatchReadyAction {...props} paused />)
  expect(
    screen.getByRole("button", { name: "Save 7 statements to Financial" })
  ).toBeDisabled()
  expect(
    screen.getByText(/Resume batch preparation before saving/)
  ).toBeVisible()
  expect(props.onConfirm).not.toHaveBeenCalled()
})

it("keeps failed reading work visible when no statement reviews exist", () => {
  render(
    <BatchProgressSummary
      files={Array.from({ length: 8 }, () => ({ status: "error" }))}
      summary={{
        ...summary,
        total: 0,
        available: 0,
        blocked: 0,
        imported: 0,
        available_no_activity: 0,
      }}
      available={0}
      imported={0}
      pending={0}
      skipped={0}
      duplicates={0}
      assigned={0}
    />
  )
  expect(screen.getByText(/8 files still need reading/)).toBeVisible()
  expect(
    screen.getByText(/8 files failed before statement review/)
  ).toBeVisible()
  expect(
    screen.getByText(
      /Zero prepared reviews does not mean this batch is finished/
    )
  ).toBeVisible()
})
it("draws one progress bar whose legend carries every non-zero count as text", () => {
  render(
    <BatchProgressSummary
      files={[{ status: "checked" }]}
      summary={{ ...summary, skipped: 2, duplicate_ignored: 1 }}
      available={0}
      imported={0}
      pending={0}
      skipped={0}
      duplicates={0}
      assigned={0}
    />
  )
  const legend = screen.getByRole("list", { name: "Batch progress by state" })
  expect(within(legend).getAllByRole("listitem").map((item) => item.textContent)).toEqual([
    "Saved to Financial: 1",
    "Ready to save: 7",
    "Need corrections or a decision: 6",
    "Left unimported or ignored: 3",
  ])
})

it("names files removed from Financial instead of counting them as still to read, as the review queue does", () => {
  // d5b330d1 batch 30231f0a (1 Nov): '214 files still need reading' while the queue counted 208 of them as removed.
  render(
    <BatchProgressSummary
      files={[
        ...Array.from({ length: 5 }, () => ({ status: "error", set_aside: "removed" })),
        { status: "error", set_aside: "gone" },
        { status: "error" },
        { status: "checked" },
      ]}
      summary={{ ...summary, total: 1, available: 0, blocked: 0, imported: 1, available_no_activity: 0 }}
      available={0}
      imported={1}
      pending={0}
      skipped={0}
      duplicates={0}
      assigned={0}
    />
  )
  expect(screen.getByText(/1 files still need reading · 5 files removed from Financial · 1 file no longer in the case/)).toBeVisible()
  expect(screen.getByText(/1 of 8 files read · 1 need a reading check · 6 set aside/)).toBeVisible()
})

it("names unsaved statements and unread files by the review queue's lists, not as work still to finish", () => {
  // d5b330d1 batch 30231f0a, 1 Nov: 25 unsaved statements were copies, fund statements, waiting for a reader and
  // unreadable; 7 failed files had been read in other batches or were copies of files already read.
  const files = [
    ...Array.from({ length: 3 }, () => ({ status: "checked" })),
    { status: "error", set_aside: "removed" },
    { status: "error", set_aside: "read_elsewhere" },
    { status: "error", set_aside: "copy" },
  ]
  render(
    <BatchProgressSummary
      files={files}
      summary={{
        ...summary,
        available: 0,
        blocked: 11,
        possible_duplicates: 14,
        queue: {
          still_to_finish: 0, updating: false, ready: 0, filled: 0, saving: 0, rechecking: 0, reader_fix: 2, unreadable: 1,
          copies: 15, not_payment: 7, left_unimported: 0, imported: 0, assigned: 0,
        },
      }}
      available={0}
      imported={0}
      pending={0}
      skipped={0}
      duplicates={0}
      assigned={0}
    />
  )
  const line = within(screen.getByLabelText("Your batch progress")).getAllByRole("status")[0]
  expect(line).toHaveTextContent(
    "1 saved to Financial · 0 prepared reviews still to finish · 2 waiting for a better reader · 1 couldn't be read · 15 copies set aside · 7 fund statements set aside · 2 files read in another batch or upload · 1 file removed from Financial"
  )
  expect(line).not.toHaveTextContent("still need reading")
  expect(screen.queryByText(/have not finished reading/)).toBeNull()
})

it("keeps its own count of statements still to finish until the queue has been built", () => {
  render(
    <BatchProgressSummary
      files={[{ status: "checked" }]}
      summary={{ ...summary, queue: null }}
      available={0}
      imported={0}
      pending={0}
      skipped={0}
      duplicates={0}
      assigned={0}
    />
  )
  expect(within(screen.getByLabelText("Your batch progress")).getAllByRole("status")[0]).toHaveTextContent(
    "1 saved to Financial · 13 prepared reviews still to finish"
  )
})

it("says when the queue's lists come from its last view while it is being updated", () => {
  render(
    <BatchProgressSummary
      files={[{ status: "checked" }]}
      summary={{
        ...summary,
        queue: {
          still_to_finish: 1, updating: true, ready: 0, filled: 0, saving: 0, rechecking: 0, reader_fix: 0,
          unreadable: 0, copies: 2, not_payment: 0, left_unimported: 0, imported: 0, assigned: 0,
        },
      }}
      available={0}
      imported={0}
      pending={0}
      skipped={0}
      duplicates={0}
      assigned={0}
    />
  )
  expect(within(screen.getByLabelText("Your batch progress")).getAllByRole("status")[0]).toHaveTextContent(
    "1 saved to Financial · 1 prepared reviews still to finish · 2 copies set aside (from the review queue's last view; it is being updated)"
  )
})

it("names statements already imported without saying they came from another file", () => {
  // Live 1 Nov: 394 of the 450 statements in the queue's imported list were the same file imported through another
  // batch; 34 were another upload of the same bytes. "From another file" was wrong for most of them.
  render(
    <BatchProgressSummary
      files={[]}
      summary={{
        ...summary,
        queue: {
          still_to_finish: 0, updating: false, ready: 0, filled: 0, saving: 0, rechecking: 0, reader_fix: 0, unreadable: 0,
          copies: 0, not_payment: 0, left_unimported: 0, imported: 3, assigned: 0,
        },
      }}
      available={0}
      imported={1}
      pending={0}
      skipped={0}
      duplicates={0}
      assigned={0}
    />
  )
  const line = within(screen.getByLabelText("Your batch progress")).getAllByRole("status")[0]
  expect(line).toHaveTextContent("· 3 already imported")
  expect(line).not.toHaveTextContent("from another file")
})
