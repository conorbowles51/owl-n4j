import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { ChatMessage } from "./ChatMessage"
import type { ChatMessageData } from "../types"

describe("ChatMessage sources", () => {
  it("opens the cited document at its page", () => {
    const onDocumentClick = vi.fn()
    const message = {
      id: "m1",
      role: "assistant",
      content: "Answer",
      sources: [{ filename: "statement.pdf", page: 4 }],
    } as unknown as ChatMessageData

    render(<ChatMessage message={message} onDocumentClick={onDocumentClick} />)
    fireEvent.click(screen.getByRole("button", { name: /1 source/ }))
    fireEvent.click(screen.getByRole("button", { name: /statement\.pdf p\.4/ }))

    expect(onDocumentClick).toHaveBeenCalledWith("statement.pdf", 4)
  })

  it("has no placeholder citation panel left to reach", () => {
    // The old CitationPanel only said a viewer 'will be integrated'; citations open the real document viewer.
    const modules = import.meta.glob("./CitationPanel.tsx")
    expect(Object.keys(modules)).toEqual([])
  })
})
