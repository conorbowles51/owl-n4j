import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { useGuardedProcess } from "../hooks/use-guarded-process"
import { ProcessHoldDialog } from "./ProcessHoldDialog"

function Harness() {
  const gate = useGuardedProcess("case-browser")
  return (
    <>
      <button
        onClick={() => void gate.start({ fileIds: ["a"], profile: "default" })}
      >
        Start selection
      </button>
      <ProcessHoldDialog gate={gate} />
    </>
  )
}

afterEach(() => vi.restoreAllMocks())

it("handles a server hold, records a decision, and processes only on a separate click", async () => {
  // Real components, hook and HTTP clients in Chromium; only service responses are fixtures.
  const originalFetch = globalThis.fetch
  const requests: string[] = []
  let processingAttempts = 0
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, options) => {
    const url = String(input)
    if (!url.startsWith("/api/")) return originalFetch(input, options)
    requests.push(url)
    const json = (body: unknown, status = 200) =>
      new Response(JSON.stringify(body), { status })
    if (url.includes("route-check"))
      return json({
        case_id: "case-browser",
        files: [
          {
            file_id: "a",
            file_name: "statement.dat",
            outcome: "not_native",
            blocks_document_processing: false,
            detected_format: null,
            claimants: [],
            reason: null,
          },
        ],
        summary: { checked: 1, native: 0, blocking: 0, outcomes: {} },
      })
    if (url.includes("/admit?")) {
      expect(JSON.parse(options?.body as string)).toEqual({
        reason: "Reviewed the source document",
      })
      return json({
        file_id: "a",
        outcome: "admitted",
        admitted: true,
        routed_to: "document_pipeline",
        reason: "Reviewed the source document",
        file_name: "statement.dat",
        route_outcome: "ambiguous",
        detected_format: null,
        claimants: ["bai2", "mt940"],
        adjudication_id: "decision-1",
      })
    }
    if (url.includes("process/background")) {
      processingAttempts++
      expect(JSON.parse(options?.body as string).file_ids).toEqual(["a"])
      if (processingAttempts === 1)
        return json(
          {
            detail: {
              error: "unadmitted_files",
              message: "Decision needed",
              held: [
                {
                  file_id: "a",
                  file_name: "statement.dat",
                  route_outcome: "ambiguous",
                  detected_format: null,
                  claimants: ["bai2", "mt940"],
                },
              ],
            },
          },
          409
        )
      return json({ task_id: "task-1" })
    }
    throw new Error(`Unexpected request: ${url}`)
  })
  render(
    <QueryClientProvider
      client={
        new QueryClient({
          defaultOptions: {
            queries: { retry: false },
            mutations: { retry: false },
          },
        })
      }
    >
      <Harness />
    </QueryClientProvider>
  )
  fireEvent.click(screen.getByRole("button", { name: "Start selection" }))
  expect(await screen.findByRole("dialog")).toBeVisible()
  expect(screen.getByText("Claimed by: BAI2, MT940")).toBeVisible()
  expect(screen.getByRole("button", { name: "Record decision" })).toBeDisabled()
  fireEvent.change(screen.getByRole("textbox"), {
    target: { value: "Reviewed the source document" },
  })
  fireEvent.click(screen.getByRole("button", { name: "Record decision" }))
  const process = await screen.findByRole("button", {
    name: "Process this file",
  })
  expect(processingAttempts).toBe(1)
  expect(
    screen.getByText("Your recorded reason: Reviewed the source document")
  ).toBeVisible()
  fireEvent.click(process)
  await waitFor(() =>
    expect(screen.getByText(/Processing requested for this file/)).toBeVisible()
  )
  expect(processingAttempts).toBe(2)
  expect(requests.filter((url) => url.includes("/admit?"))).toHaveLength(1)
  expect(screen.queryByRole("button", { name: "Process this file" })).toBeNull()
})
