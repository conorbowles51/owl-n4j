import { fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { describe, expect, it, vi } from "vitest"

/** 03 section 3.6 items 7 and 8: Show on Timeline, Show on Map (when positioned), Add to…, Correct this value and
 * Used in this case on the record panel. Synthetic data only. */
const api = vi.hoisted(() => ({ correctRecordValue: vi.fn(), getRecordUses: vi.fn() }))
vi.mock("../api", async (orig) => ({ ...(await orig<object>()), ...api }))
vi.mock("../collect-targets", () => ({ useCollectTargets: () => ({ targets: [], note: null, loading: false, error: null }) }))

import { RecordDetailView } from "./RecordPanel"
import type { RecordDetail } from "../schemas"

const base = {
  record_uid: "r-1",
  extraction: { id: "e1", label: "C1", report_filename: null, report_sha256: null },
  model_type: "InstantMessage",
  cellebrite_id: "7",
  title: null,
  state: { deleted_state: "Intact", is_carved: false, decoding_confidence: null, source_index: null, interpretation_level: "generic" },
  fields: [{ name: "Body", kind: "field", data_type: "String", values: [{ index: 0, type: "String", text: "synthetic body", empty: false }], attributes: {}, children: [] }],
  attributes: {},
  times: [],
  files: [],
  files_absence: null,
  source_row: { available: false, reason: "No source row." },
  corrections: [],
  interpretation_level: "generic",
  zone: "UTC",
  readings: [],
  as_text: "C1 InstantMessage",
  on_timeline: true,
  position: null,
  correctable: [{ field_path: "Body", value_index: 0, value_type: "String", machine_text: "synthetic body", corrected_text: null, revision: "rev0" }],
} as unknown as RecordDetail

function Where() {
  const l = useLocation()
  return <p data-testid="where">{l.pathname + l.search}</p>
}

function show(detail: RecordDetail) {
  return render(
    <MemoryRouter initialEntries={["/cases/case-1/phones/e1/records/conversations"]}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <Routes>
          <Route path="*" element={<><RecordDetailView detail={detail} caseId="case-1" /><Where /></>} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

describe("Record panel actions (03 section 3.6)", () => {
  it("Show on Timeline opens the lens on the record; Show on Map appears only when the record is positioned", () => {
    api.getRecordUses.mockResolvedValue({ target_id: "r-1", summary: null, counts: {}, uses: [] })
    const { unmount } = show(base)
    expect(screen.queryByRole("button", { name: "Show on Map" })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Show on Timeline" }))
    expect(screen.getByTestId("where")).toHaveTextContent("/cases/case-1/timeline?phone_record=r-1")
    unmount()
    show({ ...base, on_timeline: false, position: { point_uid: "p", lat: 38.9, lon: -77.03 } } as RecordDetail)
    expect(screen.queryByRole("button", { name: "Show on Timeline" })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Show on Map" }))
    expect(screen.getByTestId("where")).toHaveTextContent("/cases/case-1/map?phone_point=-77.03,38.9")
  })

  it("Used in this case reads the reverse lookup, and says so when the record is in nothing (CO-7)", async () => {
    api.getRecordUses.mockResolvedValue({
      target_id: "r-1", summary: "In 1 finding and 2 dossiers", counts: { finding: 1, dossier: 2 },
      uses: [{ kind: "finding", container_id: "f1", container_label: "Synthetic finding", via: "direct", relationship: null },
        { kind: "dossier", container_id: "d1", container_label: "Synthetic A", via: "selection", relationship: null },
        { kind: "dossier", container_id: "d2", container_label: "Synthetic B", via: "direct", relationship: null }],
    })
    show(base)
    const box = screen.getByRole("region", { name: "Used in this case" })
    expect(await within(box).findByText("1 finding and 2 dossiers")).toBeInTheDocument()
    expect(within(box).getByText("(dossier, through a saved selection)")).toBeInTheDocument()
    expect(api.getRecordUses).toHaveBeenCalledWith("case-1", "r-1")
  })

  it("Correct this value needs a reason, sends the revision it was shown, and keeps the phone's value in view (02 10.4)", async () => {
    api.getRecordUses.mockResolvedValue({ target_id: "r-1", summary: null, counts: {}, uses: [] })
    api.correctRecordValue.mockResolvedValue({ decision_id: "d1" })
    show(base)
    expect(await screen.findByText("Not yet in any finding, theory, note, dossier, interview or task.")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Correct this value" }))
    const form = screen.getByRole("form", { name: "Correct this value" })
    expect(within(form).getByText("synthetic body", { selector: "span" })).toBeInTheDocument()
    const [value, reason] = within(form).getAllByRole("textbox")
    fireEvent.change(value, { target: { value: "synthetic corrected" } })
    const save = within(form).getByRole("button", { name: "Save correction" })
    expect(save).toBeDisabled()
    fireEvent.change(reason, { target: { value: "synthetic reason" } })
    fireEvent.click(save)
    await waitFor(() =>
      expect(api.correctRecordValue).toHaveBeenCalledWith("case-1", "r-1", { field_path: "Body", value_index: 0, corrected_text: "synthetic corrected", reason: "synthetic reason", expected_revision: "rev0" }),
    )
    expect(await within(form).findByText(/^Corrected\. The phone's own value stays recorded/)).toBeInTheDocument()
  })

  it("a dated message without its own position offers Show on Map near it in time (03 section 3.6 item 7)", () => {
    api.getRecordUses.mockResolvedValue({ target_id: "r-1", summary: null, counts: {}, uses: [] })
    show({ ...base, message_dated: true } as RecordDetail)
    fireEvent.click(screen.getByRole("button", { name: "Show on Map" }))
    expect(screen.getByTestId("where")).toHaveTextContent("/cases/case-1/map?phone_near=r-1")
  })
})
