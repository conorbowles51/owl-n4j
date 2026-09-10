import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { TraceReportDownload } from "./TraceReportDownload"
import type { VerifiedTrace } from "../lib/trace-report"

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  localStorage.clear()
})
const trace = {
  envelope: {
    case_id: "case",
    scenario_json: "original",
    scenario_sha256: "a".repeat(64),
  },
} as VerifiedTrace
async function mount(changes: Record<string, string> = {}) {
  const bytes = new TextEncoder().encode("archive")
  const digest = Array.from(
    new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)),
    (b) => b.toString(16).padStart(2, "0")
  ).join("")
  const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(bytes, {
      headers: {
        "content-type": "application/zip",
        "X-Loupe-Case-Id": "case",
        "X-Loupe-Privilege-Marking": "unmarked",
        "X-Loupe-Scenario-Sha256": trace.envelope.scenario_sha256,
        "X-Loupe-Archive-Sha256": digest,
        ...changes,
      },
    })
  )
  const makeUrl = vi.fn(() => "blob:audit")
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
  const view = render(<TraceReportDownload trace={trace} />)
  return { fetch, makeUrl, click, ...view }
}
it("downloads an authenticated bundle for the captured scenario after checking integrity", async () => {
  localStorage.setItem("authToken", "test-token")
  const { fetch, click } = await mount()
  fireEvent.click(
    screen.getByRole("button", { name: "Download tracing audit bundle" })
  )
  await waitFor(() => expect(click).toHaveBeenCalledTimes(1))
  expect(String(fetch.mock.calls[0][0])).toContain(
    "trace-support-export?case_id=case"
  )
  expect(JSON.parse(fetch.mock.calls[0][1]?.body as string)).toEqual({
    scenarios: ["original"],
    privilege_marking: "unmarked",
  })
  expect(fetch.mock.calls[0][1]?.headers).toMatchObject({
    Authorization: "Bearer test-token",
  })
})
it.each<Record<string, string>>([
  { "X-Loupe-Case-Id": "other" },
  { "X-Loupe-Scenario-Sha256": "b".repeat(64) },
  { "X-Loupe-Archive-Sha256": "b".repeat(64) },
  { "X-Loupe-Privilege-Marking": "confidential" },
])("refuses a mismatched audit download %j", async (changes) => {
  const { makeUrl } = await mount(changes)
  fireEvent.click(
    screen.getByRole("button", { name: "Download tracing audit bundle" })
  )
  await screen.findByRole("alert")
  expect(makeUrl).not.toHaveBeenCalled()
})
