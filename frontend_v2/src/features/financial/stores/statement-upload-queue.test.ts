import { beforeEach, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import {
  uploadStatementFiles,
  useStatementUploads,
} from "./statement-upload-queue"
vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
beforeEach(() => {
  vi.mocked(fetchAPI).mockReset()
  useStatementUploads.setState({ queues: {} })
  useAuthStore.setState({ user: null })
})
const pdf = (name: string) =>
  new File(["synthetic"], name, { type: "application/pdf" })

it("uploads and prepares each selected file separately and keeps a per-file outcome", async () => {
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (String(url).endsWith("/upload")) {
      const file = (options?.body as FormData).get("files") as File
      return {
        files: [
          { id: file.name, case_id: "case", original_filename: file.name },
        ],
      }
    }
    return { job_ids: ["job"] }
  })
  await uploadStatementFiles(
    [pdf("first.pdf"), pdf("second.pdf")],
    "case",
    "anonymous",
    vi.fn()
  )
  const result = useStatementUploads.getState().queues["anonymous:case"]
  expect(result.running).toBe(false)
  expect(result.items.map((item) => [item.name, item.status])).toEqual([
    ["first.pdf", "Reading queued"],
    ["second.pdf", "Reading queued"],
  ])
  expect(
    vi
      .mocked(fetchAPI)
      .mock.calls.filter(([url]) => String(url).includes("process/background"))
      .map(([, options]) => options?.body)
  ).toEqual([
    {
      case_id: "case",
      file_ids: ["first.pdf"],
      preparation_mode: "pdf_review",
    },
    {
      case_id: "case",
      file_ids: ["second.pdf"],
      preparation_mode: "pdf_review",
    },
  ])
})

it("retains an uncertain failure and continues the other files without retrying it", async () => {
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (String(url).endsWith("/upload")) {
      const file = (options?.body as FormData).get("files") as File
      if (file.name === "first.pdf") throw Error("Connection lost")
      return {
        files: [
          { id: "second", case_id: "case", original_filename: file.name },
        ],
      }
    }
    return { job_ids: ["job"] }
  })
  await uploadStatementFiles(
    [pdf("first.pdf"), pdf("second.pdf")],
    "case",
    "anonymous",
    vi.fn()
  )
  const items = useStatementUploads.getState().queues["anonymous:case"].items
  expect(items[0].status).toBe("Needs attention")
  expect(items[0].error).toContain("Check the file list")
  expect(items[1].status).toBe("Reading queued")
  expect(fetchAPI).toHaveBeenCalledTimes(3)
})

it("rejects non-PDF selections before uploading anything", async () => {
  await expect(
    uploadStatementFiles([pdf("notes.txt")], "case", "anonymous", vi.fn())
  ).rejects.toThrow("PDF files only")
  expect(fetchAPI).not.toHaveBeenCalled()
})
