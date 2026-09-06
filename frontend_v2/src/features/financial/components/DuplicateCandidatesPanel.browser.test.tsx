import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { duplicateCandidates } from "@/test/duplicate-fixture"
import { DuplicateCandidatesPanel } from "./DuplicateCandidatesPanel"

afterEach(() => vi.restoreAllMocks())
it("opens candidate and coverage details in Chromium without making a write request", async () => {
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async (url, options) => {
      expect(String(url)).toBe("/api/financial/duplicates?case_id=case-1")
      expect(options?.method ?? "GET").toBe("GET")
      return new Response(JSON.stringify(duplicateCandidates()))
    })
  render(
    <QueryClientProvider client={new QueryClient()}>
      <DuplicateCandidatesPanel caseId="case-1" />
    </QueryClientProvider>
  )
  expect(fetch).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole("button", { name: "Compare documents" }))
  fireEvent.click(await screen.findByText(/Candidate group 1/))
  expect(screen.getByText("copy.ofx")).toBeVisible()
  expect(screen.getByText("Document status: superseded")).toBeVisible()
  fireEvent.click(screen.getByText("Documents not compared (1)"))
  expect(screen.getByText(/empty.pdf:/)).toBeVisible()
})
