import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { LedgerExportComparison } from "./LedgerExportComparison"
afterEach(() => {
  vi.restoreAllMocks()
  localStorage.clear()
})
const changes = { added: [], removed: [], changed: [] }
const report = {
  schema_version: "loupe.financial.export_comparison/1",
  case_id: "case",
  status: "same_captured_content",
  readings: changes,
  decisions: changes,
  pdf_review_history: {},
  export_preparation_changed: true,
  packaging_or_generation_changed: true,
  limitation: "Synthetic comparison",
}
function files() {
  fireEvent.click(screen.getByText("Compare saved ledger exports"))
  fireEvent.change(screen.getByLabelText("Earlier ledger export"), {
    target: { files: [new File(["old"], "old.zip")] },
  })
  fireEvent.change(screen.getByLabelText("Later ledger export"), {
    target: { files: [new File(["new"], "new.zip")] },
  })
}
it("uploads selected archives with case authentication and clears stale results on file change", async () => {
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValue(new Response(JSON.stringify(report)))
  localStorage.setItem("authToken", "fixture-token")
  render(<LedgerExportComparison caseId="case" />)
  files()
  fireEvent.click(
    screen.getByRole("button", { name: "Compare captured exports" })
  )
  await screen.findByRole("region", { name: "Saved export comparison" })
  expect(String(fetch.mock.calls[0][0])).toContain("case_id=case")
  expect(fetch.mock.calls[0][1]?.headers).toEqual({
    Authorization: "Bearer fixture-token",
  })
  expect(fetch.mock.calls[0][1]?.body).toBeInstanceOf(FormData)
  fireEvent.change(screen.getByLabelText("Later ledger export"), {
    target: { files: [new File(["changed"], "changed.zip")] },
  })
  expect(
    screen.queryByRole("region", { name: "Saved export comparison" })
  ).toBeNull()
})
it("refuses another case's response", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ ...report, case_id: "other" }))
  )
  render(<LedgerExportComparison caseId="case" />)
  files()
  fireEvent.click(
    screen.getByRole("button", { name: "Compare captured exports" })
  )
  expect(await screen.findByRole("alert")).toHaveTextContent("different case")
  expect(
    screen.queryByRole("region", { name: "Saved export comparison" })
  ).toBeNull()
})
it("aborts a pending comparison when its case view unmounts", async () => {
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(() => new Promise(() => {}))
  const view = render(<LedgerExportComparison caseId="case" />)
  files()
  fireEvent.click(
    screen.getByRole("button", { name: "Compare captured exports" })
  )
  await waitFor(() => expect(fetch).toHaveBeenCalledOnce())
  const signal = fetch.mock.calls[0][1]?.signal
  view.unmount()
  expect(signal?.aborted).toBe(true)
})
