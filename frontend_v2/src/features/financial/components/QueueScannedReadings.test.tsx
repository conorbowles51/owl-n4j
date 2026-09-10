import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, fireEvent } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { QueueScannedReadings } from "./QueueScannedReadings"
import {
  scanFixture,
  sourceFixture,
  mappingFixture,
} from "../lib/__fixtures__/scanned-readings"
afterEach(() => vi.restoreAllMocks())
function mount(
  fail: "none" | "preflight" | "save" = "none",
  includeUndated = false
) {
  const calls: string[] = []
  const saved = vi.fn()
  vi.spyOn(globalThis, "fetch").mockImplementation(async (url, options) => {
    const post = options?.method === "POST"
    const page = post
      ? JSON.parse(String(options.body)).page_number
      : Number(String(url).match(/pages\/(\d+)/)?.[1])
    calls.push(`${post ? "POST" : "GET"} ${page}`)
    if (fail === "save" && post && page === 2)
      throw Error("Synthetic interrupted save")
    const value = post
      ? mappingFixture(JSON.parse(String(options!.body)))
      : {
          ...sourceFixture(page),
          ...(fail === "preflight" && page === 2
            ? { source_revision: "d".repeat(64) }
            : {}),
        }
    const responseValue =
      post && includeUndated
        ? {
            ...value,
            id: `mapping-${page}-${JSON.parse(String(options!.body)).rows[0].row_index}`,
          }
        : value
    return new Response(JSON.stringify(responseValue), {
      headers: { "Content-Type": "application/json" },
    })
  })
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <QueueScannedReadings
        scan={scanFixture}
        onBusy={vi.fn()}
        onSaved={saved}
      />
    </QueryClientProvider>
  )
  if (includeUndated)
    fireEvent.click(
      screen.getByLabelText(
        "Include undated fee and interest proposals, with dates unresolved"
      )
    )
  fireEvent.click(
    screen.getByRole("button", { name: "Select all eligible scan pages" })
  )
  fireEvent.click(
    screen.getByRole("button", {
      name: "Add selected scan proposals to review",
    })
  )
  return { calls, saved }
}
it("checks every selected page before the first save and opens review only on request", async () => {
  const { calls, saved } = mount()
  await screen.findByText(/Selected proposals are available/)
  expect(calls).toEqual(["GET 1", "GET 2", "POST 1", "POST 2"])
  expect(saved).not.toHaveBeenCalled()
  fireEvent.click(
    screen.getByRole("button", { name: "Open saved review group 1 for page 1" })
  )
  expect(saved).toHaveBeenCalledWith("mapping-1")
})
it("saves nothing when a preflight source revision changed", async () => {
  const { calls } = mount("preflight")
  await screen.findByRole("alert")
  expect(calls).toEqual(["GET 1", "GET 2"])
})
it("retains confirmed pages, stops after an uncertain save and does not automatically retry", async () => {
  const { calls } = mount("save")
  await screen.findByRole("alert")
  expect(calls).toEqual(["GET 1", "GET 2", "POST 1", "POST 2"])
  expect(
    screen.getByRole("button", { name: "Open saved review group 1 for page 1" })
  ).toBeEnabled()
  expect(
    screen.getByRole("button", {
      name: "Add selected scan proposals to review",
    })
  ).toBeDisabled()
  expect(screen.getByRole("alert")).toHaveTextContent(
    "save outcome for review group 2 on page 2 must be checked"
  )
})

it("keeps dated and undated layouts in separate groups on the same page", async () => {
  const { calls } = mount("none", true)
  await screen.findByText(/Selected proposals are available/)
  expect(calls).toEqual([
    "GET 1",
    "GET 2",
    "POST 1",
    "POST 1",
    "POST 2",
    "POST 2",
  ])
  expect(
    screen.getByRole("button", { name: "Open saved review group 2 for page 1" })
  ).toBeEnabled()
  expect(
    screen.getByRole("button", { name: "Open saved review group 4 for page 2" })
  ).toBeEnabled()
})
