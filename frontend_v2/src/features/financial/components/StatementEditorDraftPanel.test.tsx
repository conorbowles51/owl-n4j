import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { StatementEditorDraftPanel } from "./StatementEditorDraftPanel"
afterEach(() => vi.restoreAllMocks())
const value = {
  group: "",
  selected: [],
  start: "2026-01-01",
  end: "",
  opening: "12.",
  closing: "",
  convention: "" as const,
  reason: "Not finished",
  cells: {},
}
const saved = {
  case_id: "case",
  evidence_file_id: "file",
  revision: "a".repeat(64),
  statement_scopes: [],
  editor_draft: value,
  applied: false,
}
function mount(data: unknown = saved) {
  const onLoad = vi.fn()
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValue(new Response(JSON.stringify(data)))
  render(
    <QueryClientProvider client={new QueryClient()}>
      <StatementEditorDraftPanel
        caseId="case"
        fileId="file"
        value={value}
        onLoad={onLoad}
      />
    </QueryClientProvider>
  )
  return { fetch, onLoad }
}
it("loads incomplete fields exactly and prevents replacing an unseen editor", async () => {
  const { onLoad } = mount()
  await screen.findByRole("button", {
    name: "Load unfinished statement editor",
  })
  expect(
    screen.getByRole("button", { name: "Save unfinished statement editor" })
  ).toBeDisabled()
  fireEvent.click(
    screen.getByRole("button", { name: "Load unfinished statement editor" })
  )
  expect(onLoad).toHaveBeenCalledWith(value)
  expect(
    screen.getByRole("button", { name: "Save unfinished statement editor" })
  ).toBeEnabled()
})
it("saves unfinished fields with the known revision and preserves reviewed scopes", async () => {
  const { fetch } = mount({ ...saved, revision: null, editor_draft: null })
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "Save unfinished statement editor" })
    ).toBeEnabled()
  )
  fetch.mockResolvedValue(new Response(JSON.stringify(saved)))
  fireEvent.click(
    screen.getByRole("button", { name: "Save unfinished statement editor" })
  )
  await screen.findByText("Unfinished editor saved.")
  const call = fetch.mock.calls.find(([, o]) => o?.method === "PUT")!
  expect(JSON.parse(String(call[1]?.body))).toEqual({
    expected_revision: null,
    statement_scopes: [],
    editor_draft: value,
  })
})
