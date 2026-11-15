import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import type { EvidenceFileRecord } from "@/types/evidence.types"
import { FileCheckNotice } from "./FileCheckNotice"
import sidebarSource from "./EvidenceContextSidebar.tsx?raw"

vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

describe("FileCheckNotice", () => {
  it("is in the evidence page's file side panel, above Details", () => {
    // it sat only in FilePreviewPanel, which no page renders (lx-citeproof 15 Nov): a held file showed its badge in
    // the list, and its side panel never said why
    const notice = sidebarSource.indexOf("<FileCheckNotice file={file} caseId={caseId} />")
    expect(notice).toBeGreaterThan(-1)
    expect(notice).toBeLessThan(sidebarSource.indexOf('<CollapsibleSection title="Details">'))
  })

  it("says why a file held in the side panel is held, with its release", () => {
    const file = {
      id: "f1", original_filename: "tool.exe", reading_hold: "held", reading_hold_reason: "program",
      file_type_words: "a Windows program",
    } as unknown as EvidenceFileRecord
    render(
      <QueryClientProvider client={new QueryClient()}>
        <FileCheckNotice file={file} caseId="c1" />
      </QueryClientProvider>,
    )
    expect(screen.getByText(/This file is program code \(a Windows program\)/)).toBeTruthy()
    expect(screen.getByRole("button", { name: "Release for reading" })).toBeTruthy()
  })
})
