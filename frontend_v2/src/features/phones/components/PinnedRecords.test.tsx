import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, within } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"

/** The pinned preview beside the Chat and Notebook composers (03 section 3.6, 07 section 4.3, CO-6). Synthetic. */
const api = vi.hoisted(() => ({ getRecord: vi.fn(), getRecordUses: vi.fn() }))
vi.mock("../api", async (orig) => ({ ...(await orig<object>()), ...api }))
vi.mock("../collect-targets", () => ({ useCollectTargets: () => ({ targets: [], note: null, loading: false, error: null }) }))
import { PhonePrefill, PinnedRecords } from "./PinnedRecords"

const detail = (uid: string) => ({
  record_uid: uid, extraction: { id: "e1", label: "C1", report_filename: null, report_sha256: null }, model_type: "InstantMessage",
  cellebrite_id: "7", title: `synthetic ${uid}`, state: { deleted_state: "Intact", is_carved: false, decoding_confidence: null, source_index: null, interpretation_level: "generic" },
  fields: [], attributes: {}, times: [{ record_uid: uid, field_path: "TimeStamp", value_index: 0, instant: "2023-03-14T19:07:00Z", full: "Tuesday, March 14, 2023 3:07 PM EDT", original_text: "x", offset_present: true }],
  files: [], files_absence: null, source_row: { available: false, reason: "No source row." }, corrections: [], interpretation_level: "generic", zone: "UTC", readings: [], as_text: "x",
})

describe("Pinned records", () => {
  it("previews the first three, counts the rest, and Open the record opens the record beside the composer", async () => {
    api.getRecord.mockImplementation(async (_c: string, uid: string) => detail(uid))
    api.getRecordUses.mockResolvedValue({ target_id: "r1", summary: null, counts: {}, uses: [] })
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter>
          <PinnedRecords caseId="c1" recordIds={["r1", "r2", "r3", "r4"]} total={412} />
        </MemoryRouter>
      </QueryClientProvider>,
    )
    const pinned = screen.getByLabelText("Pinned records")
    expect(await within(pinned).findByText("C1 · synthetic r1 · Tuesday, March 14, 2023 3:07 PM EDT")).toBeInTheDocument()
    expect(within(pinned).getAllByRole("button", { name: "Open the record" })).toHaveLength(3)
    expect(within(pinned).getByText("and 409 more")).toBeInTheDocument()
    expect(api.getRecord).toHaveBeenCalledTimes(3)
    fireEvent.click(within(pinned).getAllByRole("button", { name: "Open the record" })[1])
    expect(await screen.findByText("Record behind this message")).toBeInTheDocument()
  })

  it("the Notebook prefill says how many were selected and that all of them will be linked (CO-6)", async () => {
    api.getRecord.mockImplementation(async (_c: string, uid: string) => detail(uid))
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter>
          <PhonePrefill caseId="c1" selected={412} linked={412} recordIds={["r1", "r2"]} />
        </MemoryRouter>
      </QueryClientProvider>,
    )
    expect(screen.getByRole("status")).toHaveTextContent("412 selected; all 412 will be linked.")
    expect(await screen.findByText("and 410 more")).toBeInTheDocument()
  })
})
