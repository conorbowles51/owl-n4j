import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { TraceSupportVerification } from "./TraceSupportVerification"
afterEach(() => {
  vi.restoreAllMocks()
  localStorage.clear()
})
async function setup(overrides = {}) {
  const bytes = new TextEncoder().encode("archive").buffer
  const hash = Array.from(
    new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)),
    (b) => b.toString(16).padStart(2, "0")
  ).join("")
  const report = {
    schema_version: "loupe.financial.trace_support_verification/1",
    archive_sha256: hash,
    case_id: "case",
    member_count: 3,
    status: "verified_bytes_matching_rebuild",
    changed_members: [],
    manifest_metadata_changed: false,
    replay_version_changes: [],
    checkpoint_status: "not_supplied",
    limitation: "Synthetic verification",
    ...overrides,
  }
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValue(new Response(JSON.stringify(report)))
  const view = render(<TraceSupportVerification caseId="case" />)
  fireEvent.click(screen.getByText("Check a saved tracing audit package"))
  const file = new File([bytes], "support.zip")
  Object.defineProperty(file, "arrayBuffer", { value: async () => bytes })
  fireEvent.change(screen.getByLabelText("Tracing audit ZIP"), {
    target: { files: [file] },
  })
  return { fetch, hash, ...view }
}
it("authenticates a case-bound check and clears the result when inputs change", async () => {
  localStorage.setItem("authToken", "fixture-token")
  const { fetch } = await setup()
  fireEvent.click(screen.getByRole("button", { name: "Check package" }))
  await screen.findByRole("region", { name: "Saved package verification" })
  expect(fetch.mock.calls[0][0]).toContain(
    "trace-support-verification?case_id=case"
  )
  expect(fetch.mock.calls[0][1]?.headers).toEqual({
    Authorization: "Bearer fixture-token",
  })
  fireEvent.change(
    screen.getByLabelText("Previously saved SHA-256 (optional)"),
    { target: { value: "a" } }
  )
  expect(
    screen.queryByRole("region", { name: "Saved package verification" })
  ).toBeNull()
})
it("refuses a response for another selected file", async () => {
  await setup({ archive_sha256: "a".repeat(64) })
  fireEvent.click(screen.getByRole("button", { name: "Check package" }))
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "different file or case"
  )
})
it("shows changed support as a review result rather than a clean pass", async () => {
  await setup({
    status: "verified_bytes_different_rebuild",
    changed_members: ["scenarios/01/expert-support.json"],
  })
  fireEvent.click(screen.getByRole("button", { name: "Check package" }))
  expect(await screen.findByRole("status")).toHaveTextContent(
    "rebuilt support differs"
  )
  expect(
    screen.getByText("scenarios/01/expert-support.json")
  ).toBeInTheDocument()
})
it("refuses a mismatched independent digest before uploading", async () => {
  const { fetch } = await setup()
  fireEvent.change(
    screen.getByLabelText("Previously saved SHA-256 (optional)"),
    { target: { value: "a".repeat(64) } }
  )
  fireEvent.click(screen.getByRole("button", { name: "Check package" }))
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "differs from the previously saved digest"
  )
  expect(fetch).not.toHaveBeenCalled()
})
it("aborts pending verification when the case view unmounts", async () => {
  const { fetch, unmount } = await setup()
  fetch.mockImplementation(() => new Promise(() => {}))
  fireEvent.click(screen.getByRole("button", { name: "Check package" }))
  await waitFor(() => expect(fetch).toHaveBeenCalledOnce())
  const signal = fetch.mock.calls[0][1]?.signal
  unmount()
  expect(signal?.aborted).toBe(true)
})
