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
import { afterEach, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { uploadFingerprint } from "../resumable-upload"
import {
  uploadFolderOrArchive,
  type UploadGroup,
} from "../resumable-upload-groups"
import { MemoryRouter } from "react-router-dom"
import { StatementFilesPanel } from "@/features/financial/components/StatementFilesPanel"
import { useStatementUploads } from "@/features/financial/stores/statement-upload-queue"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import { ResumableUploadsPanel } from "./ResumableUploadsPanel"

vi.mock("@/lib/api-client", async (original) => ({
  ...(await original<typeof import("@/lib/api-client")>()),
  fetchAPI: vi.fn(),
}))
vi.mock(
  "@/features/financial/hooks/use-financial-access",
  async (original) => ({
    ...(await original<
      typeof import("@/features/financial/hooks/use-financial-access")
    >()),
    useFinancialAccess: () => ({
      canEdit: true,
      canUpload: true,
      ready: true,
      error: false,
    }),
  })
)
afterEach(cleanup)
const CHUNK = 4 * 1024 * 1024
function file(path: string, size: number, value = 42) {
  const result = new File(
    [new Uint8Array(size).fill(value)],
    path.split("/").at(-1)!
  )
  Object.defineProperty(result, "webkitRelativePath", { value: path })
  return result
}
function mount(client: QueryClient) {
  return render(
    <QueryClientProvider client={client}>
      <div className="max-w-lg p-4">
        <ResumableUploadsPanel caseId="case" />
      </div>
    </QueryClientProvider>
  )
}

it.each(["folder", "statements"] as const)(
  "pauses %s, returns to saved progress and registers once after a lost response",
  async (journey) => {
    const financial = journey === "statements"
    useAuthStore.setState({ user: null })
    useStatementUploads.setState({ queues: {} })
    await page.viewport(1280, 900)
    const paths = financial
      ? ["first.pdf", "second.pdf"]
      : ["Folder/a.txt", "Folder/sub/b.txt"]
    const files = [file(paths[0], 20), file(paths[1], CHUNK + 10)]
    const records = paths.map((path, index) => ({
      id: index ? "b" : "a",
      case_id: "case",
      original_filename: path.split("/").at(-1)!,
      status: "unprocessed",
    }))
    const readingRequests: string[] = []
    let group: UploadGroup | undefined
    let release: (() => void) | undefined
    let held = false
    let registrations = 0
    const sent: string[] = []
    const copy = () => {
      if (group) {
        group.staged_count = group.members!.filter(
          (m) => m.status === "staged" || m.status === "completed"
        ).length
        group.received_bytes = group.members!.reduce(
          (sum, m) =>
            sum +
            m.received.reduce(
              (n, i) => n + Math.min(CHUNK, m.size - i * CHUNK),
              0
            ),
          0
        )
      }
      return structuredClone(group)
    }
    vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
      if (url.startsWith("/api/financial/statement-import/files?"))
        return { case_id: "case", files: [], truncated: false }
      if (url.startsWith("/api/evidence?"))
        return { files: group?.status === "completed" ? records : [] }
      if (url === "/api/evidence/a" || url === "/api/evidence/b")
        return records.find((record) => url.endsWith("/" + record.id))
      if (url.includes("/process/background")) {
        const body = options?.body as {
          file_ids: string[]
          preparation_mode: string
        }
        expect(body.preparation_mode).toBe("pdf_review")
        readingRequests.push(...body.file_ids)
        return { job_ids: ["job-" + body.file_ids[0]] }
      }
      if (url.startsWith("/api/evidence-upload-sessions?")) return []
      if (url === "/api/evidence-upload-groups" && options?.method === "POST") {
        const body = options.body as {
          id: string
          members: { path: string; size: number; sha256: string }[]
        }
        expect(body.members.map((m) => m.path)).toEqual(paths)
        group = {
          id: body.id,
          case_id: "case",
          folder_id: null,
          name: financial ? "Selected files (2)" : "Folder",
          kind: financial ? "files" : "folder",
          replace_existing: false,
          status: "uploading",
          file_count: 2,
          staged_count: 0,
          size: CHUNK + 30,
          received_bytes: 0,
          receipt: null,
          members: body.members.map((m, index) => ({
            ...m,
            filename: m.path.split("/").at(-1)!,
            id: `member-${index}`,
            group_id: body.id,
            case_id: "case",
            folder_id: null,
            status: "uploading",
            chunk_size: CHUNK,
            received: [],
            evidence_id: null,
          })),
        }
        return copy()
      }
      if (url.startsWith("/api/evidence-upload-groups?"))
        return group && group.status !== "completed" ? [copy()] : []
      if (url.startsWith("/api/evidence-upload-groups/")) {
        if (url.endsWith("/pause") || url.endsWith("/resume")) {
          group!.status = url.endsWith("/pause") ? "paused" : "uploading"
          group!.members!.forEach((m) => {
            if (m.status !== "staged")
              m.status = group!.status === "paused" ? "paused" : "uploading"
          })
        }
        if (url.endsWith("/complete")) {
          registrations++
          expect(group!.members!.every((m) => m.status === "staged")).toBe(true)
          group!.status = "completed"
          group!.receipt = {
            file_ids: ["a", "b"],
            job_ids: [],
            message: "Uploaded 2 files. Folder structure is retained.",
          }
          throw Error("Lost final acknowledgement")
        }
        return copy()
      }
      const member = group?.members?.find((m) => url.includes(`/${m.id}`))
      if (member) {
        if (url.includes("/chunks/")) {
          const index = Number(url.split("/").at(-1))
          sent.push(`${member.id}:${index}`)
          if (member.id === "member-1" && index === 1 && !held) {
            held = true
            await new Promise<void>((resolve) => {
              release = resolve
            })
          }
          if (member.status === "paused") throw Error("Paused")
          member.received = [...new Set([...member.received, index])]
        }
        if (url.endsWith("/complete")) member.status = "staged"
        return structuredClone(member)
      }
      return []
    })
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    const refresh = () =>
      client.invalidateQueries({
        queryKey: ["resumable-upload-groups", "case"],
      })
    const mountJourney = () =>
      financial
        ? render(
            <QueryClientProvider client={client}>
              <MemoryRouter>
                <div className="p-4">
                  <StatementFilesPanel caseId="case" register />
                </div>
              </MemoryRouter>
            </QueryClientProvider>
          )
        : mount(client)
    let task: ReturnType<typeof uploadFolderOrArchive> | undefined
    try {
      mountJourney()
      if (financial)
        fireEvent.change(screen.getByLabelText("Statement PDFs"), {
          target: { files },
        })
      else task = uploadFolderOrArchive("case", files, { isFolder: true })
      await waitFor(() => expect(release).toBeTypeOf("function"), {
        timeout: 10000,
      })
      await refresh()
      fireEvent.click(
        await screen.findByRole("button", { name: "Pause upload" })
      )
      await screen.findByText("Upload paused")
      release!()
      cleanup()
      mountJourney()
      await screen.findByText("Upload paused")
      expect(screen.getByText(/1 of 2 files verified/)).toBeVisible()
      fireEvent.click(screen.getByRole("button", { name: "Resume upload" }))
      if (task)
        expect((await task).message).toContain("Folder structure is retained")
      else {
        await waitFor(() => expect(readingRequests).toEqual(["a", "b"]))
        expect(
          useStatementUploads
            .getState()
            .queues["anonymous:case"].items.map((item) => item.status)
        ).toEqual(["Reading queued", "Reading queued"])
        await screen.findByText(
          "2 PDFs in Financial · 0 with imported statements"
        )
        await page.screenshot({
          path: "/tmp/loupe-financial-upload-resumed.png",
        })
      }
      expect(registrations).toBe(1)
      expect(sent).toEqual([
        "member-0:0",
        "member-1:0",
        "member-1:1",
        "member-1:1",
      ])
      await refresh()
      await waitFor(() =>
        expect(screen.queryByText("Folder")).not.toBeInTheDocument()
      )
    } finally {
      release?.()
      cleanup()
      client.clear()
    }
  }
)

it("reselects remaining folder files after reopening, refuses changed bytes and retains completed members", async () => {
  await page.viewport(390, 844)
  const original = file("Folder/sub/b.txt", CHUNK + 10, 19)
  const fingerprint = await uploadFingerprint(original)
  const group: UploadGroup = {
    id: "reopened",
    case_id: "case",
    folder_id: null,
    name: "Folder",
    kind: "folder",
    replace_existing: false,
    status: "paused",
    file_count: 2,
    staged_count: 1,
    size: CHUNK + 30,
    received_bytes: CHUNK + 20,
    receipt: null,
    members: [
      {
        id: "done",
        path: "Folder/a.txt",
        filename: "a.txt",
        case_id: "case",
        folder_id: null,
        size: 20,
        sha256: "saved",
        chunk_size: CHUNK,
        received: [0],
        status: "staged",
        evidence_id: null,
      },
      {
        id: "remaining",
        path: "Folder/sub/b.txt",
        filename: "b.txt",
        case_id: "case",
        folder_id: null,
        size: original.size,
        sha256: fingerprint.sha256,
        chunk_size: CHUNK,
        received: [0],
        status: "paused",
        evidence_id: null,
      },
    ],
  }
  const sent: number[] = []
  vi.mocked(fetchAPI).mockImplementation(async (url) => {
    if (url.startsWith("/api/evidence-upload-sessions?")) return []
    if (url.startsWith("/api/evidence-upload-groups?"))
      return group.status === "completed" ? [] : [structuredClone(group)]
    if (url.startsWith("/api/evidence-upload-groups/")) {
      if (url.endsWith("/resume")) {
        group.status = "uploading"
        group.members![1].status = "uploading"
      }
      if (url.endsWith("/complete")) {
        group.status = "completed"
        group.receipt = {
          file_ids: ["a", "b"],
          job_ids: [],
          message: "Recovered 2 files",
        }
      }
      return structuredClone(group)
    }
    if (url.includes("/remaining")) {
      const member = group.members![1]
      if (url.includes("/chunks/")) {
        const index = Number(url.split("/").at(-1))
        sent.push(index)
        member.received.push(index)
      }
      if (url.endsWith("/complete")) member.status = "staged"
      return structuredClone(member)
    }
    throw Error(`Unexpected request: ${url}`)
  })
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  try {
    mount(client)
    await screen.findByRole("button", { name: "Reselect folder to resume" })
    const picker = screen.getByLabelText("Original folder for Folder")
    expect(picker).toHaveAttribute("webkitdirectory")
    fireEvent.change(picker, {
      target: { files: [file("Folder/sub/b.txt", original.size, 3)] },
    })
    expect(await screen.findByRole("alert")).toHaveTextContent("has changed")
    expect(sent).toEqual([])
    const bounds = screen
      .getByRole("button", { name: "Reselect folder to resume" })
      .getBoundingClientRect()
    expect(bounds.right).toBeLessThanOrEqual(390)
    fireEvent.change(picker, { target: { files: [original] } })
    await waitFor(() => expect(group.status).toBe("completed"), {
      timeout: 10000,
    })
    expect(sent).toEqual([1])
    await waitFor(() =>
      expect(screen.queryByText("Folder")).not.toBeInTheDocument()
    )
  } finally {
    cleanup()
    client.clear()
  }
})
