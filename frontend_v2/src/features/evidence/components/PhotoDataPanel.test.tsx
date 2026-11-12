import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { beforeEach, expect, it, vi } from "vitest"
import { PhotoDataPanel } from "./PhotoDataPanel"

const fetchAPI = vi.fn()
vi.mock("@/lib/api-client", () => ({ fetchAPI: (...args: unknown[]) => fetchAPI(...args) }))

function show(detail: object) {
  fetchAPI.mockImplementation((url: string, init?: { method?: string }) =>
    Promise.resolve(init?.method === "PUT" ? { caption: "ok" } : detail)
  )
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <PhotoDataPanel caseId="c" fileId="f" canEdit />
    </QueryClientProvider>
  )
}

beforeEach(() => fetchAPI.mockReset())

it("says which values the photo's data lacked and labels the rest as unchecked", async () => {
  show({ read: true, label: "From the photo's data, not checked by a person.", absent: ["place", "camera"], caption: null,
    time_words: "09:00 (UTC offset +01:00)", data: { width: 4, height: 3, date_taken: { local: "2024-05-02T09:00:00", offset: "+01:00" } } })
  expect(await screen.findByText(/not checked by a person/)).toBeTruthy()
  expect(screen.getByText("2024-05-02 09:00 (UTC offset +01:00)")).toBeTruthy()
  expect(screen.getByText("Absent from the file: place, camera.")).toBeTruthy()
})

it("saves an optional caption and asks for nothing else", async () => {
  show({ read: true, label: "x", absent: [], caption: null, time_words: null, data: { width: 1, height: 1 } })
  const input = (await screen.findByLabelText("Caption (optional)")) as HTMLInputElement
  fireEvent.change(input, { target: { value: "The pier" } })
  fireEvent.click(screen.getByText("Save caption"))
  await waitFor(() =>
    expect(fetchAPI).toHaveBeenCalledWith("/api/photos/f/caption?case_id=c", { method: "PUT", body: { caption: "The pier" } })
  )
})
