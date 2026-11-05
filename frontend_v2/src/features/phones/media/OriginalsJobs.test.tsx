import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

/** 03 8.3: Download originals, true progress and every file's outcome. Invented files. */
const api = vi.hoisted(() => ({ getOriginals: vi.fn(), cancelOriginals: vi.fn(), originalsFileUrl: (c: string, b: string) => `/file/${c}/${b}` }))
vi.mock("../api", () => api)
import { OriginalsJobs } from "./OriginalsJobs"

const page = () => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><OriginalsJobs caseId="c" /></QueryClientProvider>)
const bundle = (over: object) => ({ bundle_id: "b1", state: "running", scope_words: "C1", files_total: 3, bytes_total: 3 * 1024 ** 3, files_done: 1, bytes_done: 1024 ** 3, matched: 1, mismatched: 0, no_stored_hash: 0, not_included: 0, file: null, error: null, created_at: null, finished_at: null, expires_at: null, ...over })

describe("Download originals jobs", () => {
  it("states true progress in files and bytes while a job runs", async () => {
    api.getOriginals.mockResolvedValue({ items: [bundle({})] })
    page()
    expect(await screen.findByText("1 of 3 files, 1.0 GB of 3.0 GB.")).toBeInTheDocument()
  })

  it("says every file's outcome when finished: mismatches and files left out are never hidden", async () => {
    api.getOriginals.mockResolvedValue({ items: [bundle({ state: "done", files_done: 3, bytes_done: 10, mismatched: 1, not_included: 1, file: { filename: "x.zip", size: 2048, sha256: "ff" } })] })
    page()
    expect(await screen.findByText("3 files: 1 match every stored hash, 1 differ from a stored hash and are included, 1 could not be included. manifest.csv in the zip lists each one.")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Save the zip (2 KB)" })).toHaveAttribute("href", "/file/c/b1")
  })

  it("says so when the zip has been removed", async () => {
    api.getOriginals.mockResolvedValue({ items: [bundle({ state: "removed" })] })
    page()
    expect(await screen.findByText(/removed after its days were up/)).toBeInTheDocument()
  })
})
