import "@/styles/globals.css"
import { useState } from "react"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import { page, userEvent } from "vitest/browser"
import {
  cleanup,
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react"
import { DocumentViewer } from "./document-viewer"
import { resetPageImagesForTests } from "./pdf-page-images"

const requests: number[] = []
let totalPages = 1928
let failedPage: number | null = null
let pageSize = { width: 600, height: 1000 }
let delayMs = 0
vi.mock("@/lib/protected-file", () => ({
  useProtectedObjectUrl: () => ({
    objectUrl: null,
    loading: false,
    error: null,
  }),
  openProtectedFile: vi.fn(),
}))

beforeEach(() => {
  resetPageImagesForTests()
  requests.length = 0
  totalPages = 1928
  failedPage = null
  pageSize = { width: 600, height: 1000 }
  delayMs = 0
  localStorage.setItem("loupeSession", "synthetic-user")
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, options: RequestInit) => {
      const pageNumber = Number(url.match(/\/page\/(\d+)\/image/)?.[1])
      expect(options.credentials).toBe("include")
      requests.push(pageNumber)
      if (pageNumber === failedPage) return new Response(null, { status: 503 })
      const canvas = document.createElement("canvas")
      if (delayMs) await new Promise((resolve) => setTimeout(resolve, delayMs))
      canvas.width = pageSize.width
      canvas.height = pageSize.height
      const context = canvas.getContext("2d")!
      context.fillStyle = "white"
      context.fillRect(0, 0, pageSize.width, pageSize.height)
      context.fillStyle = "black"
      context.font = "28px sans-serif"
      context.fillText(`Synthetic page ${pageNumber}`, 30, 60)
      const blob = await new Promise<Blob>((resolve) =>
        canvas.toBlob((blob) => resolve(blob!), "image/png")
      )
      return new Response(blob, {
        headers: {
          "content-type": "image/png",
          "X-PDF-Page-Count": String(totalPages),
        },
      })
    })
  )
})
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function Viewer({ initialPage = 1 }: { initialPage?: number }) {
  const [open, setOpen] = useState(true)
  return (
    <DocumentViewer
      open={open}
      onOpenChange={setOpen}
      evidenceId="synthetic-pdf"
      documentUrl="/synthetic.pdf"
      documentName="synthetic.pdf"
      initialPage={initialPage}
    />
  )
}

it("scrolls across PDF pages, updates navigation and keeps a long document bounded", async () => {
  await page.viewport(1440, 1000)
  render(<Viewer />)
  await screen.findByRole("img", { name: "Page 1 of the original PDF" })
  await screen.findByText("Page 1 of 1928")
  const region = screen.getByRole("region", { name: "PDF document pages" })
  await waitFor(() =>
    expect(region.scrollHeight).toBeGreaterThan(region.clientHeight)
  )
  expect(
    screen.getByRole("button", { name: "Previous PDF page" })
  ).toBeDisabled()
  region.focus()
  await act(async () => {
    await userEvent.keyboard("{PageDown}{PageDown}{PageDown}")
  })
  await waitFor(() => expect(region.scrollTop).toBeGreaterThan(0))
  await waitFor(() => expect(screen.queryByText("Page 1 of 1928")).toBeNull())
  expect(
    screen.getByRole("button", { name: "Previous PDF page" })
  ).not.toBeDisabled()
  fireEvent.click(screen.getByRole("button", { name: "Next PDF page" }))
  fireEvent.click(screen.getByRole("button", { name: "Zoom in PDF page" }))
  expect(screen.getByText("125%")).toBeVisible()
  fireEvent.click(screen.getByRole("button", { name: "Fit page width" }))
  expect(screen.getByText("100%")).toBeVisible()
  await waitFor(() => {
    const pages = screen.queryAllByRole('img')
    expect(pages.length).toBeGreaterThan(0)
    expect(pages.length).toBeLessThan(12)
  })
  expect(new Set(requests).size).toBeLessThan(20)
  fireEvent.click(screen.getByRole("button", { name: "Close document" }))
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull())
})

it("opens the cited page and permits scrolling back to earlier pages", async () => {
  await page.viewport(1280, 800)
  render(<Viewer initialPage={12} />)
  await screen.findByRole("img", { name: "Page 12 of the original PDF" })
  expect(screen.getByText("Page 12 of 1928")).toBeVisible()
  expect(requests).not.toContain(1)
  fireEvent.click(screen.getByRole("button", { name: "Previous PDF page" }))
  await screen.findByText("Page 11 of 1928")
  expect(
    await screen.findByRole("img", { name: "Page 11 of the original PDF" })
  ).toBeVisible()
})

it("opens a later page on a narrow screen and stays on it while the pages before it load", async () => {
  // As live (13 Nov, OPDMD66 statement 2): letter-size pages that take a while each.
  await page.viewport(390, 844)
  pageSize = { width: 1275, height: 1650 }
  delayMs = 400
  render(<Viewer initialPage={5} />)
  await screen.findByRole("img", { name: "Page 5 of the original PDF" })
  // The list measures the pages it mounted and settles with page 5 at the top, and the page shown stays 5.
  const region = screen.getByRole("region", { name: "PDF document pages" })
  await waitFor(
    () => {
      const fifth = region.querySelector<HTMLElement>('[data-index="4"]')
      expect(fifth).not.toBeNull()
      expect(
        Math.abs(fifth!.getBoundingClientRect().top - region.getBoundingClientRect().top)
      ).toBeLessThan(40)
    },
    { timeout: 10000 }
  )
  await new Promise((resolve) => setTimeout(resolve, 1500))
  const fifth = region.querySelector<HTMLElement>('[data-index="4"]')!
  expect(Math.abs(fifth.getBoundingClientRect().top - region.getBoundingClientRect().top)).toBeLessThan(40)
  expect(screen.getByText("Page 5 of 1928")).toBeVisible()
})

it("retries a failed page while retaining the surrounding document", async () => {
  await page.viewport(1280, 800)
  totalPages = 3
  failedPage = 2
  render(<Viewer />)
  await screen.findByRole("img", { name: "Page 1 of the original PDF" })
  await screen.findByText(/Page 2 could not be loaded/)
  failedPage = null
  fireEvent.click(screen.getByRole("button", { name: "Retry page" }))
  await screen.findByRole("img", { name: "Page 2 of the original PDF" })
})
