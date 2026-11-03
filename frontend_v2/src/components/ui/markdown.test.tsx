import { render, screen } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { describe, expect, it } from "vitest"
import { Markdown } from "./markdown"

const UID = "3af41de3-c6aa-4b1e-9d0e-2f4f0df3ffe5"

function inCase(content: string) {
  return render(
    <MemoryRouter initialEntries={["/cases/case-1/chat"]}>
      <Routes>
        <Route path="/cases/:id/chat" element={<Markdown content={content} />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe("Markdown citations", () => {
  it("a rec:// citation is a link that opens the phone record in this case (S-6)", () => {
    inCase(`See [C3 WhatsApp message, Tue, Mar 14, 2023](rec://${UID}).`)
    expect(screen.getByRole("link", { name: /C3 WhatsApp message/ })).toHaveAttribute("href", `/cases/case-1/records/${UID}`)
  })
  it("a doc:// citation with no page still opens the document and claims no page (S-6)", () => {
    inCase("From [Synthetic ledger](doc://synthetic-ledger.pdf).")
    const b = screen.getByRole("button", { name: "Synthetic ledger" })
    expect(b.textContent).not.toMatch(/p\.\s?1/)
  })
})
