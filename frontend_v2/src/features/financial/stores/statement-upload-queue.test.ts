import { beforeEach, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import { uploadFolderOrArchive } from "@/features/evidence/resumable-upload-groups"
import {
  uploadStatementFiles,
  useStatementUploads,
} from "./statement-upload-queue"
vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
vi.mock("@/features/evidence/resumable-upload-groups", () => ({
  uploadFolderOrArchive: vi.fn(),
}))
beforeEach(() => {
  vi.mocked(fetchAPI).mockReset()
  vi.mocked(uploadFolderOrArchive).mockReset()
  useStatementUploads.setState({ queues: {} })
  useAuthStore.setState({ user: null })
})
const pdf = (name: string) =>
  new File(["synthetic"], name, { type: "application/pdf" })

it("retains the upload selection and prepares each registered PDF with a per-file outcome", async () => {
  vi.mocked(uploadFolderOrArchive).mockResolvedValue({
    file_ids: ["first.pdf", "second.pdf"],
  })
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (!options?.method) {
      const name = url.split("/").at(-1)!
      return { id: name, case_id: "case", original_filename: name }
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

it("retains a reading failure and continues the other already uploaded PDFs", async () => {
  vi.mocked(uploadFolderOrArchive).mockResolvedValue({
    file_ids: ["first.pdf", "second.pdf"],
  })
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (!options?.method) {
      const name = url.split("/").at(-1)!
      return { id: name, case_id: "case", original_filename: name }
    }
    if ((options.body as { file_ids: string[] }).file_ids[0] === "first.pdf")
      throw Error("Connection lost")
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
  expect(fetchAPI).toHaveBeenCalledTimes(4)
})

it("an interrupted upload retains all selected names and never starts an incomplete selection", async () => {
  vi.mocked(uploadFolderOrArchive).mockRejectedValue(
    Error("Connection lost; received parts are saved")
  )
  await expect(
    uploadStatementFiles(
      [pdf("first.pdf"), pdf("second.pdf")],
      "case",
      "anonymous",
      vi.fn()
    )
  ).rejects.toThrow("Connection lost")
  const result = useStatementUploads.getState().queues["anonymous:case"]
  expect(result.running).toBe(false)
  expect(result.items.map((item) => item.status)).toEqual([
    "Upload needs attention",
    "Upload needs attention",
  ])
  expect(result.items[0].error).toContain("Resume the saved selection")
  expect(fetchAPI).not.toHaveBeenCalled()
})

it("rejects non-PDF selections before uploading anything", async () => {
  await expect(
    uploadStatementFiles([pdf("notes.txt")], "case", "anonymous", vi.fn())
  ).rejects.toThrow("PDF files only")
  expect(fetchAPI).not.toHaveBeenCalled()
})
