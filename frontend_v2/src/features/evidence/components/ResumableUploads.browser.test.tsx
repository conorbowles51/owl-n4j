import "@/styles/globals.css"
import { page } from "vitest/browser"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react"
import { expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import {
  uploadOrdinaryFiles,
  uploadFingerprint,
  type UploadSession,
} from "../resumable-upload"
import { JobsPanel } from "./JobsPanel"

vi.mock("@/lib/api-client", async (original) => ({
  ...(await original<typeof import("@/lib/api-client")>()),
  fetchAPI: vi.fn(),
}))
vi.mock("../hooks/use-job-progress", () => ({ useJobProgress: vi.fn() }))
vi.mock("../hooks/use-guarded-process", () => ({
  useGuardedProcess: () => ({ start: vi.fn() }),
}))
vi.mock("./ProcessHoldDialog", () => ({ ProcessHoldDialog: () => null }))

it("pauses an upload, retains saved bytes after leaving, and recovers a lost completion receipt", async () => {
  await page.viewport(1280, 900)
  const file = new File(
    [new Uint8Array(4 * 1024 * 1024 + 100).fill(42)],
    "Synthetic chat.pdf",
    { type: "application/pdf" }
  )
  let stored: UploadSession | undefined
  let release: (() => void) | undefined
  let completeCount = 0
  let firstSecondChunk = true
  const sent: number[] = []
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (url.startsWith("/api/background-tasks?")) return { tasks: [] }
    if (url.startsWith("/api/evidence/engine/jobs?")) return []
    if (url === "/api/evidence-upload-sessions" && options?.method === "POST") {
      const body = options.body as UploadSession
      stored = {
        ...body,
        status: "uploading",
        chunk_size: 4 * 1024 * 1024,
        received: [],
        evidence_id: null,
      }
      return structuredClone(stored)
    }
    if (url.startsWith("/api/evidence-upload-sessions?"))
      return stored && stored.status !== "completed"
        ? [structuredClone(stored)]
        : []
    if (url.includes("/chunks/")) {
      const index = Number(url.split("/").at(-1))
      sent.push(index)
      expect(options?.body).toBeInstanceOf(Blob)
      if (index === 1 && firstSecondChunk) {
        firstSecondChunk = false
        await new Promise<void>((resolve) => {
          release = resolve
        })
        if (stored!.status === "paused") throw Error("Upload paused")
      }
      stored!.received = [...new Set([...stored!.received, index])]
      return structuredClone(stored)
    }
    if (url.endsWith("/pause")) {
      stored!.status = "paused"
      return structuredClone(stored)
    }
    if (url.endsWith("/resume")) {
      stored!.status = "uploading"
      return structuredClone(stored)
    }
    if (url.endsWith("/complete")) {
      completeCount++
      stored!.status = "completed"
      stored!.evidence_id = "saved-file"
      throw Error("Synthetic lost completion response")
    }
    if (url.startsWith("/api/evidence-upload-sessions/"))
      return structuredClone(stored)
    if (url === "/api/evidence/saved-file")
      return { id: "saved-file", original_filename: file.name }
    return []
  })
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const mount = () =>
    render(
      <QueryClientProvider client={client}>
        <div className="h-[800px] max-w-xl p-4">
          <JobsPanel caseId="case" />
        </div>
      </QueryClientProvider>
    )
  const refresh = () =>
    client.invalidateQueries({ queryKey: ["resumable-uploads", "case"] })
  let transfer: ReturnType<typeof uploadOrdinaryFiles> | undefined
  try {
    mount()
    transfer = uploadOrdinaryFiles("case", [file])
    await waitFor(() => expect(release).toBeTypeOf("function"), {
      timeout: 10000,
    })
    await refresh()
    await screen.findByText("Uploading")
    expect(screen.queryByText("No processing activity")).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Pause upload" }))
    await screen.findByText("Upload paused")
    release!()
    await waitFor(() => expect(sent).toEqual([0, 1]))
    cleanup()
    mount()
    await screen.findByText("Upload paused")
    expect(screen.getByText(/4.0 of 4.0 MB saved/)).toBeVisible()
    fireEvent.click(screen.getByRole("button", { name: "Resume upload" }))
    const result = await transfer
    expect(result.files?.map((f) => f.id)).toEqual(["saved-file"])
    expect(sent).toEqual([0, 1, 1])
    expect(completeCount).toBe(1)
    await refresh()
    await waitFor(() =>
      expect(screen.queryByText(file.name)).not.toBeInTheDocument()
    )
  } finally {
    release?.()
    cleanup()
    client.clear()
  }
})

it("reselects after a fresh browser session, rejects a different file, and sends only missing chunks", async () => {
  await page.viewport(1280, 900)
  const file = new File(
    [new Uint8Array(4 * 1024 * 1024 + 200).fill(19)],
    "Interrupted example.pdf",
    { type: "application/pdf" }
  )
  const fingerprint = await uploadFingerprint(file)
  const stored: UploadSession = {
    id: "restart-upload",
    case_id: "case",
    folder_id: null,
    filename: file.name,
    size: file.size,
    sha256: fingerprint.sha256,
    chunk_size: 4 * 1024 * 1024,
    received: [0],
    status: "paused",
    evidence_id: null,
  }
  const sent: number[] = []
  vi.mocked(fetchAPI).mockImplementation(async (url) => {
    if (url.startsWith("/api/background-tasks?")) return { tasks: [] }
    if (url.startsWith("/api/evidence/engine/jobs?")) return []
    if (url.startsWith("/api/evidence-upload-sessions?"))
      return stored.status === "completed" ? [] : [structuredClone(stored)]
    if (url.endsWith("/resume")) {
      stored.status = "uploading"
      return structuredClone(stored)
    }
    if (url.includes("/chunks/")) {
      const index = Number(url.split("/").at(-1))
      sent.push(index)
      stored.received.push(index)
      return structuredClone(stored)
    }
    if (url.endsWith("/complete")) {
      stored.status = "completed"
      stored.evidence_id = "recovered-file"
      return structuredClone(stored)
    }
    if (url.startsWith("/api/evidence-upload-sessions/"))
      return structuredClone(stored)
    return []
  })
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  try {
    render(
      <QueryClientProvider client={client}>
        <JobsPanel caseId="case" />
      </QueryClientProvider>
    )
    await screen.findByRole("button", { name: "Reselect file to resume" })
    const picker = screen.getByLabelText(`Original file for ${file.name}`)
    fireEvent.change(picker, {
      target: { files: [new File(["different"], file.name)] },
    })
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "This is a different file"
    )
    expect(sent).toEqual([])
    fireEvent.change(picker, { target: { files: [file] } })
    await waitFor(() => expect(stored.status).toBe("completed"), {
      timeout: 10000,
    })
    expect(sent).toEqual([1])
    await waitFor(() =>
      expect(screen.queryByText(file.name)).not.toBeInTheDocument()
    )
  } finally {
    cleanup()
    client.clear()
  }
})
