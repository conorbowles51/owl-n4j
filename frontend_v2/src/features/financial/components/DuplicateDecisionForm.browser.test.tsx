import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { duplicateCandidates } from "@/test/duplicate-fixture"
import { DuplicateCandidatesPanel } from "./DuplicateCandidatesPanel"

afterEach(() => vi.restoreAllMocks())
it("excludes then restores a reviewed copy through the connected controls", async () => {
  let excluded = false
  const writes: string[] = []
  vi.spyOn(globalThis, "fetch").mockImplementation(async (url, options) => {
    expect(String(url)).toContain("case_id=case-1")
    if (options?.method === "POST") {
      const body = JSON.parse(String(options.body))
      expect(body.reason).toBe("Reviewed both source files")
      expect(body.expected_revision).toMatch(/^[a-f0-9]{64}$/)
      writes.push(body.action)
      excluded = body.action === "exclude"
      return new Response(
        JSON.stringify({
          case_id: "case-1",
          document_id: "copy",
          action: body.action,
          applied: true,
          changed_rows: 2,
          adjudication_id: `event-${writes.length}`,
        })
      )
    }
    const data = duplicateCandidates()
    const copy = data.groups[0].members[1]
    copy.status = excluded ? "superseded" : "admitted"
    copy.superseded_by_id = excluded ? "first" : null
    copy.rows_by_status = excluded ? { superseded: 2 } : { admitted: 2 }
    copy.revision = (excluded ? "c" : "a").repeat(64)
    data.excluded_documents = excluded ? [copy] : []
    return new Response(JSON.stringify(data))
  })
  render(
    <QueryClientProvider client={new QueryClient()}>
      <DuplicateCandidatesPanel caseId="case-1" />
    </QueryClientProvider>
  )
  fireEvent.click(screen.getByRole("button", { name: "Compare documents" }))
  fireEvent.click(await screen.findByText(/Candidate group 1/))
  fireEvent.click(
    screen.getByRole("button", {
      name: "Exclude this copy; retain original.ofx",
    })
  )
  fireEvent.change(screen.getByRole("textbox"), {
    target: { value: "Reviewed both source files" },
  })
  fireEvent.click(screen.getByRole("button", { name: "Record decision" }))
  expect(
    await screen.findByText("Decision recorded. 2 rows excluded.")
  ).toBeVisible()
  fireEvent.click(screen.getByRole("button", { name: "Close decision" }))
  fireEvent.click(await screen.findByText("Excluded documents (1)"))
  fireEvent.click(screen.getByRole("button", { name: "Restore copy.ofx" }))
  fireEvent.change(screen.getByRole("textbox"), {
    target: { value: "Reviewed both source files" },
  })
  fireEvent.click(screen.getByRole("button", { name: "Record decision" }))
  expect(
    await screen.findByText("Decision recorded. 2 rows restored.")
  ).toBeVisible()
  expect(writes).toEqual(["exclude", "restore"])
})
