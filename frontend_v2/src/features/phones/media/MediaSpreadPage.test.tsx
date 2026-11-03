import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"

const time = (source: "message_time" | "exif_capture", full: string, words: string, has_offset = true) => ({ source, source_words: words, field: source === "exif_capture" ? "EXIFCaptureTime" : "message", instant: has_offset ? "2023-03-14T12:00:00Z" : null, full, has_offset })
const copy = (over: object) => ({
  file_uid: "f1", extraction_id: "e1", phone_label: "C1", filename: "synthetic-a.jpg", local_path: "files/Image/synthetic-a.jpg", original_path: "/sdcard/DCIM/Camera/synthetic-a.jpg",
  category: "Image", size: 10, sha256: null, verification: "no_hash", verification_words: "Present; no hash stated to check", missing: false,
  included_because: ["carried by a message"], times: [], earliest: null, roles: [], messages: [], note: null, camera: null, in_camera_folder: false,
  camera_original_candidate: false, camera_original_words: null, place: null, ...over,
})
const sent = copy({ times: [time("message_time", "Tue, Mar 14, 2023, 12:00:00 PM UTC", "time of the message that carried it")], earliest: time("message_time", "Tue, Mar 14, 2023, 12:00:00 PM UTC", "time of the message that carried it"), roles: ["sent"],
  messages: [{ message_record_uid: "m1", kind: "message", direction: "outgoing", role: "sent", instant: "2023-03-14T12:00:00Z", full: "Tue, Mar 14, 2023, 12:00:00 PM UTC", app: "WhatsApp", deleted: false, line: "Owner -> +1 202-555-0143" }] })
const received = copy({ file_uid: "f2", extraction_id: "e2", phone_label: "C2", roles: ["received"], camera: { make: "SyntheticMaker", model: "Model 0" }, camera_original_candidate: null,
  camera_original_words: "Cannot tell: the capture time has no time zone, and it is too close to the first message in this group to say which came first.",
  times: [time("exif_capture", "Tue, Mar 14, 2023, 11:00:00 AM, no offset in report", "photo capture time (EXIF)", false)],
  messages: [{ message_record_uid: "m2", kind: "message", direction: "incoming", role: "received", instant: "2023-03-14T12:05:00Z", full: "Tue, Mar 14, 2023, 12:05:00 PM UTC", app: "WhatsApp", deleted: true, line: "+1 202-555-0143 -> Owner" }] })
const group = {
  group_key: "a".repeat(32), md5: "a".repeat(32), phone_count: 2, copy_count: 2, phones_with_hash: 3, case_phone_count: 4, common_file: true,
  common_words: "Common file: the same file is on 3 of the case's 4 phones. Stickers and forwarded images are often shared by people with no link to each other.",
  sha256_disagrees: false, sha256_words: null, category: "Image", filename: "synthetic-a.jpg", size: 10, thumbnail_file_uid: "f1", clock_offset_unknown: true,
  clock_words: "Times are each phone's own clock.", camera_original_candidates: 0, tier: "exact",
  phones: [
    { extraction_id: "e1", phone_label: "C1", position: 1, earliest: sent.earliest, roles: ["sent"], camera_original_candidate: false, copy_count: 1, copies_shown: 1, copies_words: null, copies: [sent] },
    { extraction_id: "e2", phone_label: "C2", position: null, earliest: null, roles: ["received"], camera_original_candidate: false, copy_count: 25, copies_shown: 1, copies_words: "20 of 25 copies on this phone shown; open the phone's Media to see every one.", copies: [received] },
  ],
}

const api = vi.hoisted(() => ({
  getMediaSpreadIndex: vi.fn(),
  getMediaSpreadWindow: vi.fn(),
  getMediaDetail: vi.fn().mockResolvedValue({ file_uid: "f2", extraction_id: "e2", category: "Image", local_path: "files/Image/synthetic-a.jpg", size: 10, hashes: {}, verification: "no_hash", verification_words: "Present; no hash stated to check", missing: false, missing_words: null, deleted_state: null, is_carved: false, message_count: 1, messages: [] }),
  mediaObjectUrl: vi.fn().mockRejectedValue(new Error("not in a browser")),
  getDerivedTexts: vi.fn().mockResolvedValue({ file_uid: "f2", items: [] }),
}))
vi.mock("../api", async (orig) => ({ ...(await orig<object>()), ...api }))
vi.mock("../collect-targets", () => ({ useCollectTargets: () => ({ targets: [], note: null, loading: false, error: null }) }))
import MediaSpreadPage from "./MediaSpreadPage"

const page = () => render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter initialEntries={["/cases/c/phones/e1/records/media/spread"]}>
      <Routes><Route path="/cases/:id/phones/:extraction/records/media/spread" element={<MediaSpreadPage />} /></Routes>
    </MemoryRouter>
  </QueryClientProvider>,
)

describe("Media spread (05 section 11, exact tier)", () => {
  it("states the true totals, lists the phones in order with the time source, sent and received, flags, and opens a copy in the file panel", async () => {
    api.getMediaSpreadIndex.mockResolvedValue({ case_id: "c", case_phone_count: 4, total_groups: 1, total_copies: 2, common_file_groups: 1, sha256_disagreement_groups: 0,
      by_phone: [{ extraction_id: "e1", label: "C1", groups: 1 }, { extraction_id: "e2", label: "C2", groups: 1 }], by_pair: [{ a: { extraction_id: "e1", label: "C1" }, b: { extraction_id: "e2", label: "C2" }, groups: 1 }],
      population_words: "Only files sent or received in a message are compared.", clock_words: "Times are each phone's own clock." })
    api.getMediaSpreadWindow.mockResolvedValue({ case_id: "c", total: 1, offset: 0, limit: 50, items: [group], clock_words: "Times are each phone's own clock." })
    page()
    expect(await screen.findByText(/^1 file is on two or more of the case's 4 phones \(2 copies\)\. 1 of them are common files/)).toBeInTheDocument()
    expect(api.getMediaSpreadWindow).toHaveBeenCalledWith("c", { phones: ["e1"], common: "all" }, 0, 50)
    const list = await screen.findByRole("list", { name: "Files on several phones" })
    expect(within(list).getByText(group.common_words)).toBeInTheDocument()
    const order = within(list).getByRole("list", { name: "Order the phones held it" })
    const [first, second] = within(order).getAllByRole("listitem").filter((li) => li.parentElement === order)
    expect(first).toHaveTextContent("1. C1: first held Tue, Mar 14, 2023, 12:00:00 PM UTC (time of the message that carried it); sent")
    expect(second).toHaveTextContent("C2: no time with a time zone to place it in the order; received; 25 copies")
    expect(within(second).getByText("20 of 25 copies on this phone shown; open the phone's Media to see every one.")).toBeInTheDocument()
    expect(within(second).getByText(/not used for the order/)).toBeInTheDocument()
    expect(within(second).getByText(/^Cannot tell:/)).toBeInTheDocument()
    expect(within(second).getByText(/message marked deleted/)).toBeInTheDocument()
    expect(within(first).getByRole("link", { name: "Sent on WhatsApp" })).toHaveAttribute("href", "/cases/c/records/m1")
    fireEvent.click(within(second).getByRole("button", { name: "Open synthetic-a.jpg" }))
    const panel = await screen.findByRole("complementary", { name: "File" })
    await waitFor(() => expect(api.getMediaDetail).toHaveBeenCalledWith("c", "f2"))
    expect(within(panel).getByText("Present; no hash stated to check")).toBeInTheDocument()
  })

  it("asks the server again when the filters change, and says so when nothing matches", async () => {
    api.getMediaSpreadIndex.mockResolvedValue({ case_id: "c", case_phone_count: 2, total_groups: 0, total_copies: 0, common_file_groups: 0, sha256_disagreement_groups: 0, by_phone: [], by_pair: [], population_words: "p", clock_words: "k" })
    api.getMediaSpreadWindow.mockResolvedValue({ case_id: "c", total: 0, offset: 0, limit: 50, items: [], clock_words: "k" })
    page()
    expect(await screen.findByText("No files match.")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("checkbox", { name: /Only files on/ }))
    fireEvent.change(screen.getByRole("combobox", { name: /Common files/ }), { target: { value: "hide" } })
    await waitFor(() => expect(api.getMediaSpreadWindow).toHaveBeenLastCalledWith("c", { phones: [], common: "hide" }, 0, 50))
  })
})
