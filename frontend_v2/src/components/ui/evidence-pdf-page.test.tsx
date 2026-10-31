import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import { EvidencePdfPage } from "./evidence-pdf-page"
import { resetPageImagesForTests } from "./pdf-page-images"

const fetchFile = vi.fn()
const createUrl = vi.fn(() => "blob:page")
const revokeUrl = vi.fn()
function imageResponse(count = 3, size = "1200x1553") {
  return {
    ok: true,
    headers: new Headers({
      "content-type": "image/png",
      "X-PDF-Page-Count": String(count),
      "X-PDF-Page-Image-Size": size,
    }),
    blob: async () => new Blob(["synthetic page"], { type: "image/png" }),
  }
}
beforeEach(() => {
  vi.stubGlobal("fetch", fetchFile)
  vi.stubGlobal(
    "URL",
    class extends URL {
      static createObjectURL = createUrl
      static revokeObjectURL = revokeUrl
    }
  )
  localStorage.setItem("authToken", "test-user")
  resetPageImagesForTests()
  fetchFile.mockReset()
  createUrl.mockClear()
  revokeUrl.mockClear()
})
afterEach(() => vi.unstubAllGlobals())

it("loads the authenticated page and reports its actual page count", async () => {
  fetchFile.mockResolvedValue(imageResponse())
  const count = vi.fn()
  const view = render(
    <EvidencePdfPage evidenceId="file-a" page={2} onPageCount={count} />
  )
  expect(
    await screen.findByRole("img", { name: "Page 2 of the original PDF" })
  ).toHaveAttribute("src", "blob:page")
  expect(fetchFile.mock.calls[0][0]).toBe("/api/evidence/file-a/page/2/image")
  expect(fetchFile.mock.calls[0][1].headers.Authorization).toBe(
    "Bearer test-user"
  )
  expect(count).toHaveBeenCalledWith("file-a", 3)
  fireEvent.click(screen.getByRole("button", { name: "Zoom in PDF page" }))
  expect(screen.getByRole("img")).toHaveStyle({ width: "125%" })
  view.unmount()
  expect(revokeUrl).toHaveBeenCalledWith("blob:page")
})

it("shows a failed page request and retries without closing the original", async () => {
  fetchFile
    .mockResolvedValueOnce({ ok: false, status: 503 })
    .mockResolvedValueOnce(imageResponse())
  render(<EvidencePdfPage evidenceId="file-a" page={2} onPageCount={vi.fn()} />)
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Page 2 could not be loaded"
  )
  fireEvent.click(screen.getByRole("button", { name: "Retry page" }))
  expect(await screen.findByRole("img")).toBeVisible()
  expect(fetchFile).toHaveBeenCalledTimes(2)
})

it("discards an old page response when the source changes", async () => {
  let finish!: (value: unknown) => void
  fetchFile
    .mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve
        })
    )
    .mockResolvedValueOnce(imageResponse(5))
  const count = vi.fn()
  const view = render(
    <EvidencePdfPage evidenceId="file-a" page={2} onPageCount={count} />
  )
  view.rerender(
    <EvidencePdfPage evidenceId="file-b" page={4} onPageCount={count} />
  )
  expect(
    await screen.findByRole("img", { name: "Page 4 of the original PDF" })
  ).toBeVisible()
  finish(imageResponse())
  await waitFor(() => expect(fetchFile).toHaveBeenCalledTimes(2))
  expect(count).toHaveBeenCalledExactlyOnceWith("file-b", 5)
  expect(createUrl).toHaveBeenCalledTimes(1)
})

it("refuses a successful HTML response instead of showing it as a PDF page", async () => {
  fetchFile.mockResolvedValue({
    ok: true,
    headers: new Headers({ "content-type": "text/html" }),
  })
  render(<EvidencePdfPage evidenceId="file-a" page={1} onPageCount={vi.fn()} />)
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "did not return a PDF page"
  )
  expect(createUrl).not.toHaveBeenCalled()
})

it("fetches a page once for the first-page view and the list's own row, and reports its size", async () => {
  fetchFile.mockResolvedValue(imageResponse())
  const size = vi.fn()
  const first = render(
    <EvidencePdfPage evidenceId="file-a" page={1} onPageCount={vi.fn()} onPageSize={size} />
  )
  await screen.findByRole("img")
  expect(size).toHaveBeenCalledWith({ width: 1200, height: 1553 })
  first.unmount()
  render(<EvidencePdfPage evidenceId="file-a" page={1} onPageCount={vi.fn()} inline />)
  await screen.findByRole("img")
  expect(fetchFile).toHaveBeenCalledTimes(1)
})

it("keeps a page still loading at the page's own shape", () => {
  fetchFile.mockReturnValue(new Promise(() => undefined))
  render(
    <EvidencePdfPage
      evidenceId="file-a"
      page={3}
      onPageCount={vi.fn()}
      inline
      documentZoom={100}
      placeholderSize={{ width: 1200, height: 1553 }}
    />
  )
  const placeholder = screen.getByRole("status").parentElement!
  expect(placeholder.style.aspectRatio).toBe("1200 / 1553")
  expect(placeholder.style.width).toBe("100%")
})
