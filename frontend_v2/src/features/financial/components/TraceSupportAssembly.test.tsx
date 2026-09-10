import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { TraceSupportAssembly } from "./TraceSupportAssembly"
afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  localStorage.clear()
})
async function sha(value: ArrayBuffer) {
  return Array.from(
    new Uint8Array(await crypto.subtle.digest("SHA-256", value)),
    (b) => b.toString(16).padStart(2, "0")
  ).join("")
}
async function mount(wrongInputs = false) {
  const source = new TextEncoder().encode("scenario").buffer,
    archive = new TextEncoder().encode("archive").buffer
  const inputDigest = await sha(
    new TextEncoder().encode(
      JSON.stringify({
        ledger: null,
        predictions: null,
        review: null,
        scenarios: [await sha(source)],
      })
    ).buffer
  )
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValue(
      new Response(archive, {
        headers: {
          "content-type": "application/zip",
          "X-Loupe-Case-Id": "case",
          "X-Loupe-Privilege-Marking": "unmarked",
          "X-Loupe-Archive-Sha256": await sha(archive),
          "X-Loupe-Assembly-Inputs-Sha256": wrongInputs
            ? "a".repeat(64)
            : inputDigest,
        },
      })
    )
  const makeUrl = vi.fn(() => "blob:review")
  vi.stubGlobal(
    "URL",
    class extends URL {
      static createObjectURL = makeUrl
      static revokeObjectURL = vi.fn()
    }
  )
  const click = vi
    .spyOn(HTMLAnchorElement.prototype, "click")
    .mockImplementation(() => {})
  const view = render(<TraceSupportAssembly caseId="case" />)
  fireEvent.click(screen.getByText("Assemble a review package"))
  const file = new File([source], "scenario.json")
  Object.defineProperty(file, "arrayBuffer", { value: async () => source })
  fireEvent.change(screen.getByLabelText("Saved tracing scenarios (JSON)"), {
    target: { files: [file] },
  })
  return { fetch, click, makeUrl, ...view }
}
it("downloads a case- and input-bound package after checking the response digest", async () => {
  localStorage.setItem("authToken", "fixture-token")
  const { fetch, click } = await mount()
  fireEvent.click(
    screen.getByRole("button", { name: "Prepare and download review package" })
  )
  expect(await screen.findByRole("status")).toHaveTextContent(
    "prepared and checked"
  )
  expect(click).toHaveBeenCalledOnce()
  expect(fetch.mock.calls[0][1]?.headers).toEqual({
    Authorization: "Bearer fixture-token",
  })
  expect(
    (fetch.mock.calls[0][1]?.body as FormData).getAll("scenarios")
  ).toHaveLength(1)
})
it("refuses a ZIP response bound to different selected inputs", async () => {
  const { click } = await mount(true)
  fireEvent.click(
    screen.getByRole("button", { name: "Prepare and download review package" })
  )
  expect(await screen.findByRole("alert")).toHaveTextContent("does not match")
  expect(click).not.toHaveBeenCalled()
})
it("does not upload a review record without its predictions", async () => {
  const { fetch } = await mount()
  fireEvent.click(
    screen.getByText("Attach reviewed extraction validation (optional)")
  )
  fireEvent.change(screen.getByLabelText("Reconciled review record (JSON)"), {
    target: { files: [new File(["{}"], "review.json")] },
  })
  fireEvent.click(
    screen.getByRole("button", { name: "Prepare and download review package" })
  )
  expect(await screen.findByRole("alert")).toHaveTextContent("Attach both")
  expect(fetch).not.toHaveBeenCalled()
})
it("cancels an in-flight assembly when its case view closes", async () => {
  const { fetch, unmount } = await mount()
  fetch.mockImplementation(() => new Promise(() => {}))
  fireEvent.click(
    screen.getByRole("button", { name: "Prepare and download review package" })
  )
  await waitFor(() => expect(fetch).toHaveBeenCalledOnce())
  const signal = fetch.mock.calls[0][1]?.signal
  unmount()
  expect(signal?.aborted).toBe(true)
})
