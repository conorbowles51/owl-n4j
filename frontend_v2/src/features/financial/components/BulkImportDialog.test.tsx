import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { expect, it, vi } from "vitest"
import type { Transaction } from "../api"
import { BulkImportDialog } from "./BulkImportDialog"

const transactions = ["a", "b"].map((key, i) => ({
  key,
  amount: (i + 1) * 100,
  currency: "EUR",
  from_entity: { key: null, name: null },
  to_entity: { key: null, name: null },
  financial_record_kind: "transaction",
  financial_view_mode: "transaction",
  is_financial_event: true,
  is_evidence_backed_transaction: true,
})) as Transaction[]
function setup(submit = vi.fn().mockResolvedValue({})) {
  const close = vi.fn()
  return {
    ...render(
      <BulkImportDialog
        open
        onOpenChange={close}
        transactions={transactions}
        onSubmit={submit}
      />
    ),
    close,
    submit,
  }
}
function choose(content: string | Promise<string>, name = "corrections.csv") {
  const file = new File([], name)
  Object.defineProperty(file, "text", { value: () => Promise.resolve(content) })
  fireEvent.change(screen.getByLabelText("Correction file"), {
    target: { files: [file] },
  })
}
const csv = "key,amount,reason\na,125,Checked the printed amount"
const apply = () => screen.getByRole("button", { name: /Apply .* corrections/ })

it("clears an earlier valid preview as soon as an invalid replacement is selected", async () => {
  const { submit } = setup()
  choose(csv)
  await screen.findByRole("table", { name: "Correction file preview" })
  choose("key,amount,reason\na,100,")
  expect(screen.queryByRole("table")).not.toBeInTheDocument()
  await screen.findByRole("alert")
  expect(
    screen.queryByRole("button", { name: /Apply .* corrections/ })
  ).not.toBeInTheDocument()
  expect(submit).not.toHaveBeenCalled()
})

it("ignores a slower earlier file after a newer file finishes", async () => {
  setup()
  let first!: (text: string) => void
  choose(
    new Promise<string>((resolve) => {
      first = resolve
    }),
    "first.csv"
  )
  choose("key,amount,reason\nb,225,Second file", "second.csv")
  await screen.findByText("Second file")
  await act(async () => first(csv))
  expect(screen.getByText("Second file")).toBeVisible()
  expect(
    screen.queryByText("Checked the printed amount")
  ).not.toBeInTheDocument()
})

it("refuses unknown record keys and workbooks instead of silently skipping them", async () => {
  setup()
  choose("key,amount,reason\nmissing,125,Checked")
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "not in the current list"
  )
  choose(csv, "corrections.xlsx")
  await waitFor(() =>
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Save an Excel workbook as CSV"
    )
  )
  expect(screen.queryByRole("table")).not.toBeInTheDocument()
})

it("submits exact keys and expected amounts once, keeps partial results visible and blocks close while saving", async () => {
  let resolve!: (value: unknown) => void
  const submit = vi.fn(
    () =>
      new Promise((done) => {
        resolve = done
      })
  )
  const { close } = setup(submit)
  choose(csv + "\nb,225,Checked receipt")
  await screen.findByRole("table")
  const button = apply()
  fireEvent.click(button)
  fireEvent.click(button)
  for (const button of screen.getAllByRole("button", { name: "Close" }))
    fireEvent.click(button)
  expect(close).not.toHaveBeenCalled()
  expect(submit).toHaveBeenCalledExactlyOnceWith([
    {
      node_key: "a",
      new_amount: 125,
      correction_reason: "Checked the printed amount",
      expected_amount: 100,
    },
    {
      node_key: "b",
      new_amount: 225,
      correction_reason: "Checked receipt",
      expected_amount: 200,
    },
  ])
  await act(async () =>
    resolve({
      success: false,
      corrected: 1,
      errors: 1,
      total: 2,
      results: [
        { key: "a", status: "corrected", old_amount: 100, new_amount: 125 },
        { key: "b", status: "error", reason: "Amount changed after preview" },
      ],
    })
  )
  expect(screen.getByRole("status")).toHaveTextContent(
    "1 of 2 corrections saved. 1 failed."
  )
  expect(screen.getByText("b: Amount changed after preview")).toBeVisible()
  expect(
    screen.queryByRole("button", { name: /Apply .* corrections/ })
  ).not.toBeInTheDocument()
  expect(close).not.toHaveBeenCalled()
})

it("does not report success or allow an immediate repeat after a lost save response", async () => {
  setup(vi.fn().mockRejectedValue(new Error("Response lost")))
  choose(csv)
  await screen.findByRole("table")
  fireEvent.click(apply())
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "A correction may have been saved"
  )
  expect(
    screen.queryByRole("button", { name: /Apply .* corrections/ })
  ).not.toBeInTheDocument()
})

it.each(["not stated", null])(
  "previews unreadable or missing amount %j and submits its exact guard",
  async (original) => {
    const submit = vi.fn().mockResolvedValue({
      success: true,
      corrected: 1,
      errors: 0,
      total: 1,
      results: [
        {
          key: "unknown",
          status: "corrected",
          old_amount: null,
          old_raw_amount: original,
          new_amount: 125,
        },
      ],
    })
    render(
      <BulkImportDialog
        open
        onOpenChange={vi.fn()}
        transactions={[
          {
            ...transactions[0],
            key: "unknown",
            amount: null,
            raw_amount: original,
          },
        ]}
        onSubmit={submit}
      />
    )
    choose("key,amount,reason\nunknown,125,Checked the original file")
    expect(
      await screen.findByText(original === null ? /\(blank\)/ : /not stated/)
    ).toBeVisible()
    fireEvent.click(apply())
    await waitFor(() =>
      expect(submit).toHaveBeenCalledWith([
        expect.objectContaining({
          node_key: "unknown",
          new_amount: 125,
          expected_raw_amount: original,
          expected_amount: undefined,
        }),
      ])
    )
  }
)
