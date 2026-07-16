import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { InvestigativeNotesSection } from "./InvestigativeNotesSection"

const notesMocks = vi.hoisted(() => ({
  mutate: vi.fn(),
  useNotes: vi.fn(),
  useCreateNote: vi.fn(),
}))

vi.mock("../hooks/use-workspace", () => ({
  useNotes: notesMocks.useNotes,
  useCreateNote: notesMocks.useCreateNote,
}))

vi.mock("./NoteDetailSheet", () => ({
  NoteDetailSheet: () => null,
}))

type CreateNoteOptions = {
  onSuccess: () => void
  onError: (error: Error) => void
}

describe("InvestigativeNotesSection", () => {
  beforeEach(() => {
    notesMocks.mutate.mockReset()
    notesMocks.useNotes.mockReset()
    notesMocks.useCreateNote.mockReset()

    vi.stubGlobal("crypto", {
      randomUUID: vi.fn(() => "11111111-2222-3333-4444-555555555555"),
    })

    notesMocks.useNotes.mockReturnValue({
      data: [],
      isLoading: false,
    })
    notesMocks.useCreateNote.mockReturnValue({
      mutate: notesMocks.mutate,
      isPending: false,
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("keeps a failed draft visible and retries with the same recovery key", async () => {
    notesMocks.mutate
      .mockImplementationOnce((_payload: unknown, options: CreateNoteOptions) => {
        options.onError(new Error("The request timed out"))
      })
      .mockImplementationOnce((_payload: unknown, options: CreateNoteOptions) => {
        options.onSuccess()
      })

    render(<InvestigativeNotesSection caseId="case-1" />)

    fireEvent.click(screen.getByRole("button"))
    fireEvent.change(screen.getByPlaceholderText("Note title"), {
      target: { value: "Witness interview" },
    })
    fireEvent.change(screen.getByPlaceholderText("Note content..."), {
      target: { value: "Witness confirmed the timeline." },
    })
    fireEvent.change(screen.getByPlaceholderText("Tags (comma-separated)"), {
      target: { value: "interview, timeline" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Save" }))

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Note was not confirmed saved.",
    )
    expect(screen.getByDisplayValue("Witness confirmed the timeline.")).toBeInTheDocument()
    expect(notesMocks.mutate).toHaveBeenCalledWith(
      {
        note_id: "note_111111112222333344445555",
        title: "Witness interview",
        content: "Witness confirmed the timeline.",
        tags: ["interview", "timeline"],
      },
      expect.any(Object),
    )

    fireEvent.click(screen.getByRole("button", { name: /Retry/ }))

    expect(notesMocks.mutate).toHaveBeenLastCalledWith(
      {
        note_id: "note_111111112222333344445555",
        title: "Witness interview",
        content: "Witness confirmed the timeline.",
        tags: ["interview", "timeline"],
      },
      expect.any(Object),
    )
    await waitFor(() => {
      expect(screen.queryByRole("alert")).not.toBeInTheDocument()
    })
    expect(screen.queryByPlaceholderText("Note content...")).not.toBeInTheDocument()
  })
})
