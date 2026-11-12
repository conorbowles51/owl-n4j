import "@/styles/globals.css"
import { useState } from "react"
import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { page } from "vitest/browser"
import { afterEach, expect, it, vi } from "vitest"
import { agentAPI } from "../api"
import { AgentBriefAttachment, type AgentBrief } from "./AgentBriefAttachment"

vi.mock("../api", () => ({ agentAPI: { previewBrief: vi.fn() } }))
afterEach(cleanup)
function Fixture({ changed = () => {} }: { changed?: (brief: AgentBrief | null) => void }) {
  const [brief, setBrief] = useState<AgentBrief | null>(null)
  return <div className="p-6"><AgentBriefAttachment brief={brief} disabled={false} onChange={(next) => { setBrief(next); changed(next) }} /></div>
}

it("shows the complete extracted template and warnings, then removes it", async () => {
  await page.viewport(390, 844)
  const changed = vi.fn()
  const text = "Report requirements\n" + "Detailed instruction.\n".repeat(500) + "Final table row: all sources"
  vi.mocked(agentAPI.previewBrief).mockResolvedValue({ filename: "template.docx", text, format: "docx", characters: text.length, warnings: ["Layout is represented as text; review headings and tables."] })
  render(<Fixture changed={changed} />)
  fireEvent.change(screen.getByLabelText("Attach a brief"), { target: { files: [new File(["synthetic"], "template.docx")] } })
  expect(await screen.findByText(/template.docx ·/)).toBeVisible()
  expect(screen.getByText("Layout is represented as text; review headings and tables.")).toBeVisible()
  expect(screen.getByText(/Final table row: all sources/).textContent).toBe(text)
  expect(changed).toHaveBeenCalledWith(expect.objectContaining({ name: "template.docx", text }))
  expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(390)
  await page.getByRole("button", { name: "Remove", exact: true }).click()
  expect(changed).toHaveBeenLastCalledWith(null)
  expect(screen.queryByText(/template.docx ·/)).not.toBeInTheDocument()
})

it("explains a scanned PDF failure and allows a complete text brief to replace it", async () => {
  await page.viewport(1440, 950)
  vi.mocked(agentAPI.previewBrief).mockRejectedValue(new Error("This PDF has no selectable text. Use Evidence for OCR or attach a text brief."))
  render(<Fixture />)
  fireEvent.change(screen.getByLabelText("Attach a brief"), { target: { files: [new File(["synthetic"], "scanned.pdf")] } })
  expect(await screen.findByRole("alert")).toHaveTextContent("no selectable text")
  fireEvent.change(screen.getByLabelText("Attach a brief"), { target: { files: [new File(["Full replacement brief"], "replacement.md")] } })
  expect(await screen.findByText("Full replacement brief")).toBeVisible()
  expect(screen.queryByRole("alert")).not.toBeInTheDocument()
})
