import { type PropsWithChildren, type ReactElement } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { InvestigativeNotesSection } from "./InvestigativeNotesSection"

const apiMocks = vi.hoisted(() => ({
  createNote: vi.fn(),
  getNotes: vi.fn(),
}))

vi.mock("../api", () => ({
  workspaceAPI: {
    createNote: apiMocks.createNote,
    getNotes: apiMocks.getNotes,
  },
}))

vi.mock("./NoteDetailSheet", () => ({
  NoteDetailSheet: () => null,
}))

function renderWithClient(ui: ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })

  function Wrapper({ children }: PropsWithChildren) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )
  }

  return render(ui, { wrapper: Wrapper })
}

describe("InvestigativeNotesSection", () => {
  beforeEach(() => {
    apiMocks.createNote.mockReset()
    apiMocks.getNotes.mockReset()
  })

  it("creates a note and shows the durable refreshed result", async () => {
    const createdNote = {
      id: "note-created",
      note_id: "note-created",
      title: "Follow-up interview",
      content: "Call the witness again",
      tags: ["witness"],
      updated_at: "2026-07-16T12:00:00Z",
    }
    apiMocks.getNotes.mockResolvedValueOnce([]).mockResolvedValueOnce([createdNote])
    apiMocks.createNote.mockResolvedValue(createdNote)

    renderWithClient(<InvestigativeNotesSection caseId="case-1" />)

    expect(await screen.findByText("No notes yet")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "Add note" }))
    fireEvent.change(screen.getByPlaceholderText("Note title"), {
      target: { value: "Follow-up interview" },
    })
    fireEvent.change(screen.getByPlaceholderText("Note content..."), {
      target: { value: "Call the witness again" },
    })
    fireEvent.change(screen.getByPlaceholderText("Tags (comma-separated)"), {
      target: { value: "witness" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Save" }))

    await waitFor(() => {
      expect(apiMocks.createNote).toHaveBeenCalledWith("case-1", {
        title: "Follow-up interview",
        content: "Call the witness again",
        tags: ["witness"],
      })
    })
    expect(await screen.findByText("Follow-up interview")).toBeInTheDocument()
    expect(screen.getByText("Call the witness again")).toBeInTheDocument()
    expect(screen.queryByText("No notes yet")).not.toBeInTheDocument()
    expect(screen.queryByPlaceholderText("Note title")).not.toBeInTheDocument()
  })

  it("keeps existing notes and draft content visible when create fails", async () => {
    const existingNote = {
      id: "note-existing",
      note_id: "note-existing",
      title: "Existing lead",
      content: "original content",
      tags: [],
      updated_at: "2026-07-16T12:00:00Z",
    }
    apiMocks.getNotes.mockResolvedValue([existingNote])
    apiMocks.createNote.mockRejectedValue(new Error("simulated save failure"))

    renderWithClient(<InvestigativeNotesSection caseId="case-1" />)

    expect(await screen.findByText("Existing lead")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "Add note" }))
    fireEvent.change(screen.getByPlaceholderText("Note title"), {
      target: { value: "Failed new lead" },
    })
    fireEvent.change(screen.getByPlaceholderText("Note content..."), {
      target: { value: "failed content" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Save" }))

    await waitFor(() => {
      expect(apiMocks.createNote).toHaveBeenCalledTimes(1)
    })
    expect(apiMocks.getNotes).toHaveBeenCalledTimes(1)
    expect(screen.getByText("Existing lead")).toBeInTheDocument()
    expect(screen.getAllByText("original content")).toHaveLength(1)
    expect(screen.getByDisplayValue("Failed new lead")).toBeInTheDocument()
    expect(screen.getByDisplayValue("failed content")).toBeInTheDocument()
  })
})
