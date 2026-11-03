import { fireEvent, render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { describe, expect, it, vi } from "vitest"

/** 05 section 3.8: a sensitive value is masked until Reveal; the reveal goes to the server, which logs it. */
const api = vi.hoisted(() => ({ revealValue: vi.fn() }))
vi.mock("../api", async (orig) => ({ ...(await orig<object>()), ...api }))

import { RecordDetailView } from "./RecordPanel"
import type { RecordDetail } from "../schemas"

const detail = {
  record_uid: "r-1",
  extraction: { id: "e1", label: "C1", report_filename: null, report_sha256: null },
  model_type: "Password",
  cellebrite_id: "7",
  title: null,
  state: { deleted_state: "Intact", is_carved: false, decoding_confidence: "High", source_index: null, interpretation_level: "generic" },
  fields: [
    { name: "Service", kind: "field", data_type: "String", values: [{ index: 0, type: "String", text: "synthetic-bank.test", empty: false }], attributes: {}, children: [] },
    { name: "Data", kind: "field", data_type: "String", sensitive: true, values: [{ index: 0, type: "String", text: "••••", empty: false, masked: true }], attributes: {}, children: [] },
  ],
  attributes: {},
  times: [],
  files: [],
  files_absence: null,
  source_row: { available: false, reason: "No source row." },
  corrections: [],
  interpretation_level: "generic",
  zone: "UTC",
  readings: [],
  as_text: "C1 Password",
} as unknown as RecordDetail

describe("Record panel sensitive values", () => {
  it("shows the mask, and the value only after Reveal", async () => {
    api.revealValue.mockResolvedValue({ value: "hunter2-synthetic", logged: true })
    render(
      <MemoryRouter>
        <QueryClientProvider client={new QueryClient()}>
          <RecordDetailView detail={detail} caseId="case-1" />
        </QueryClientProvider>
      </MemoryRouter>,
    )
    expect(screen.getByLabelText("Hidden sensitive value")).toHaveTextContent("••••")
    expect(screen.queryByText("hunter2-synthetic")).not.toBeInTheDocument()
    expect(screen.getByText("Sensitive. Revealing it records your name and the time.")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Reveal" }))
    expect(await screen.findByText("hunter2-synthetic")).toBeInTheDocument()
    expect(api.revealValue).toHaveBeenCalledWith("case-1", "r-1", "Data", 0)
    expect(screen.getByText("(revealed; your reveal is recorded)")).toBeInTheDocument()
  })
})
