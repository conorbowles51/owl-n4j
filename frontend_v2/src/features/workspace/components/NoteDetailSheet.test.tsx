import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { ApiError } from "@/lib/api-client"
import { NoteDetailSheet } from "./NoteDetailSheet"

const sheetMocks = vi.hoisted(() => ({
  buildMutate: vi.fn(),
  deleteMutate: vi.fn(),
  updateMutate: vi.fn(),
}))

vi.mock("../hooks/use-workspace", () => ({
  useBuildWorkspaceGraph: () => ({
    isPending: false,
    mutate: sheetMocks.buildMutate,
  }),
  useDeleteNote: () => ({
    isPending: false,
    mutate: sheetMocks.deleteMutate,
  }),
  useUpdateNote: () => ({
    isPending: false,
    mutate: sheetMocks.updateMutate,
  }),
}))

describe("NoteDetailSheet conflicts", () => {
  beforeEach(() => {
    sheetMocks.buildMutate.mockReset()
    sheetMocks.deleteMutate.mockReset()
    sheetMocks.updateMutate.mockReset()
  })

  it("keeps the local draft and retries with the current server version", async () => {
    const close = vi.fn()
    const conflictError = new ApiError("Version conflict", 409, {
      detail: {
        code: "workspace_version_conflict",
        entity: "note",
        current_version: 2,
        current: {
          id: "note-1",
          note_id: "note-1",
          title: "Server title",
          content: "Server edit",
          tags: ["server"],
          version: 2,
        },
      },
    })

    sheetMocks.updateMutate
      .mockImplementationOnce((_variables, options) => {
        options.onError(conflictError)
      })
      .mockImplementationOnce(() => {})

    render(
      <MemoryRouter>
        <NoteDetailSheet
          caseId="case-1"
          note={{
            id: "note-1",
            note_id: "note-1",
            title: "Local title",
            content: "Local original",
            tags: ["local"],
            version: 1,
          }}
          open
          onOpenChange={close}
        />
      </MemoryRouter>,
    )

    fireEvent.change(screen.getByDisplayValue("Local original"), {
      target: { value: "Local edit" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Save" }))

    expect(await screen.findByText("Current saved version")).toBeInTheDocument()
    expect(screen.getByText(/Server edit/)).toBeInTheDocument()
    expect(screen.getByText(/Local edit/, { selector: "pre" })).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "Merge manually" }))
    fireEvent.click(screen.getByRole("button", { name: "Save" }))

    await waitFor(() => expect(sheetMocks.updateMutate).toHaveBeenCalledTimes(2))
    expect(sheetMocks.updateMutate.mock.calls[1][0]).toMatchObject({
      noteId: "note-1",
      updates: {
        content: "Local edit",
        expected_version: 2,
      },
    })
    expect(close).not.toHaveBeenCalled()
  })

  it("blocks closing while dirty and allows it after reverting changes", () => {
    const close = vi.fn()

    render(
      <MemoryRouter>
        <NoteDetailSheet
          caseId="case-1"
          note={{
            id: "note-1",
            note_id: "note-1",
            title: "Local title",
            content: "Local original",
            tags: ["local"],
            version: 1,
          }}
          open
          onOpenChange={close}
        />
      </MemoryRouter>,
    )

    fireEvent.change(screen.getByDisplayValue("Local original"), {
      target: { value: "Local edit" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Close" }))

    expect(close).not.toHaveBeenCalled()

    fireEvent.change(screen.getByDisplayValue("Local edit"), {
      target: { value: "Local original" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Close" }))

    expect(close).toHaveBeenCalledWith(false)
  })
})
