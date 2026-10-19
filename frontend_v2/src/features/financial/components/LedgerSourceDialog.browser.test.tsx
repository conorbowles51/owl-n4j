// This existing workflow fixture has case editing and upload access.
vi.mock("../hooks/use-financial-access", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../hooks/use-financial-access")>()),
  useFinancialAccess: () => ({
    canEdit: true,
    canUpload: true,
    ready: true,
    error: false,
  }),
}))
import { MemoryRouter } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { LedgerSourceDialog } from "./LedgerSourceDialog"

afterEach(() => vi.restoreAllMocks())
it("fetches the resolved evidence page, draws its stored rectangle and opens the file in Chromium", async () => {
  const fileId = "11111111-1111-4111-8111-111111111111"
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async (url) => {
      if (String(url).includes("/ledger/"))
        return new Response(
          JSON.stringify({
            case_id: "case",
            transaction_id: "row",
            ref_id: "TX-TEST",
            source_document_id: "financial-doc",
            evidence_file_id: fileId,
            filename: "synthetic.pdf",
            sha256_at_ingestion: "a".repeat(64),
            recorded_digest_matches: true,
            file_bytes_verified: false,
            locator_state: "stored",
            locator: {
              kind: "page_rectangle",
              page: 2,
              rect: [100, 200, 300, 400],
              page_size: [1000, 1000],
              units: "millipoints",
              space: "pdf_displayed",
            },
            ledger_status: "quarantined",
            superseded_by_id: null,
            limitation: "Stored citation only.",
          })
        )
      if (String(url).includes("/page/"))
        return new Response(
          new Blob(
            [
              Uint8Array.from(
                atob(
                  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aZ1cAAAAASUVORK5CYII="
                ),
                (c) => c.charCodeAt(0)
              ),
            ],
            { type: "image/png" }
          ),
          { headers: { "Content-Type": "image/png", "X-PDF-Page-Count": "3" } }
        )
      return new Response(
        new Blob(["%PDF-1.4\n%%EOF"], { type: "application/pdf" })
      )
    })
  render(
    <MemoryRouter>
      <QueryClientProvider client={new QueryClient()}>
        <LedgerSourceDialog
          caseId="case"
          transactionId="row"
          onClose={vi.fn()}
        />
      </QueryClientProvider>
    </MemoryRouter>
  )
  const box = await screen.findByRole("img", {
    name: "Highlighted source of TX-TEST on page 2",
  })
  expect((box as HTMLElement).style.left).toBe("10%")
  expect((box as HTMLElement).style.top).toBe("20%")
  expect((box as HTMLElement).style.width).toBe("20%")
  expect((box as HTMLElement).style.height).toBe("20%")
  expect(
    fetch.mock.calls.some(([url]) =>
      String(url).includes(`/api/evidence/${fileId}/page/2/image`)
    )
  ).toBe(true)
  fireEvent.click(screen.getByRole("button", { name: "Open source file" }))
  await screen.findByRole("heading", { name: "synthetic.pdf" })
  expect(
    await screen.findByRole("img", { name: "Page 2 of the original PDF" })
  ).toBeVisible()
  expect(screen.getByText("Page 2 of 3")).toBeVisible()
  expect(document.querySelector("iframe")).toBeNull()
  fireEvent.click(screen.getByRole("button", { name: "Next PDF page" }))
  expect(
    await screen.findByRole("img", { name: "Page 3 of the original PDF" })
  ).toBeVisible()
  expect(screen.getByRole("button", { name: "Next PDF page" })).toBeDisabled()
  fireEvent.click(screen.getByRole("button", { name: "Close document" }))
  expect(
    await screen.findByRole("heading", { name: "Transaction details" })
  ).toBeVisible()
})
