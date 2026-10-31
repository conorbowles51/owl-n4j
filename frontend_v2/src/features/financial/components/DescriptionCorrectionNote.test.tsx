import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { DescriptionCorrectionNote } from "./DescriptionCorrectionNote"

describe("DescriptionCorrectionNote", () => {
  it("shows a model's first-line correction as the model's, not confirmed, with the saved text", () => {
    render(
      <DescriptionCorrectionNote
        correction={{
          before: "T20 SPEI RECIDOBANORTE",
          after: "T20 SPEI RECIBIDOBANORTE",
          previous_description: "T20 SPEI RECIDOBANORTE 0998406ARRSA",
          page: 9,
          model: "DeepSeek",
          model_id: "deepseek-flash",
          for_name: "Neil Byrne",
          confirmed: false,
        }}
      />
    )
    const note = screen.getByRole("note", { name: "Description corrected by a model" })
    expect(note.textContent).toContain("First line corrected by DeepSeek (for Neil Byrne) · not confirmed.")
    expect(note.textContent).toContain("page 9")
    expect(note.textContent).toContain("T20 SPEI RECIDOBANORTE")
    expect(note.textContent).toContain("As saved before: T20 SPEI RECIDOBANORTE 0998406ARRSA")
    expect(note.textContent).not.toMatch(/Neil Byrne · /)
  })

  it("shows nothing for a payment no model corrected", () => {
    const { container } = render(<DescriptionCorrectionNote />)
    expect(container.textContent).toBe("")
  })
})
