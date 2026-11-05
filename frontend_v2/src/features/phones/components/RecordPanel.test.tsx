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

describe("Record panel: the captured record in full (05 section 17.1)", () => {
  it("opens a nested Party with its message and chat, names the report's producer, and shows a file's paths and hashes", () => {
    const party = {
      ...detail, model_type: "Party", fields: [],
      extraction: { ...detail.extraction, producer: "Synthetic Reader 7.1", report_version: "5.2", extraction_type: "Logical" },
      parents: [{ record_uid: "m-1", model_type: "InstantMessage", title: "Synthetic hello" }, { record_uid: "c-1", model_type: "Chat", title: "Synthetic chat" }],
      attributes: { id: "7", isrelated: "False", extractionId: "0" },
      files: [{ record_uid: "r-1", file_uid: null, mechanism: "jump_target", reference: "f-9", path: null, original_path: "/sdcard/DCIM/synthetic.jpg",
        category: null, size: null, verification: "missing", badge: "File missing from production",
        absence: "The report refers to a file that is not in the production.",
        hashes: { stated_md5: "0".repeat(32), stated_sha256: "1".repeat(64), computed_md5: null, computed_sha256: null } }],
    } as unknown as RecordDetail
    render(
      <MemoryRouter>
        <QueryClientProvider client={new QueryClient()}>
          <RecordDetailView detail={party} caseId="case-1" />
        </QueryClientProvider>
      </MemoryRouter>,
    )
    const inside = screen.getByRole("region", { name: "Inside" })
    expect(inside.textContent).toContain("InstantMessage: Synthetic hello")
    expect(inside.textContent).toContain("Chat: Synthetic chat")
    expect(screen.getByTestId("record-producer").textContent).toBe("Made by Synthetic Reader 7.1, report version 5.2, Logical extraction")
    expect(screen.getByTestId("record-attributes").textContent).toContain("isrelated")
    expect(screen.getByText("On the phone at /sdcard/DCIM/synthetic.jpg")).toBeInTheDocument()
    expect(screen.getByTestId("file-hashes").textContent).toContain("MD5 in the report " + "0".repeat(32))
    expect(screen.getByText("The report refers to a file that is not in the production.")).toBeInTheDocument()
    expect(document.body.textContent).not.toMatch(/—/)
  })
})

describe("Record panel: copies from another source (02 decision 39)", () => {
  const show = (over: object) =>
    render(
      <MemoryRouter>
        <QueryClientProvider client={new QueryClient()}>
          <RecordDetailView detail={{ ...detail, ...over } as RecordDetail} caseId="case-1" />
        </QueryClientProvider>
      </MemoryRouter>,
    )

  it("marks a copy and says it is not a second source", () => {
    show({ is_copy: true, copy_of: { record_uid: "o", model_type: "VisitedPage", title: "owner" }, state: { ...detail.state, source_index: "2" } })
    expect(screen.getByTestId("record-copy")).toHaveTextContent("A copy from another source (source index 2)")
    expect(screen.getByTestId("record-copy")).toHaveTextContent("it is not a second source of the same fact")
  })

  it("lists an owner's copies, and marks nothing on a record with none", () => {
    show({ is_copy: false, related_copies: [{ record_uid: "c", model_type: "VisitedPage", title: "VisitedPage a", source_index: "3" }] })
    expect(screen.getByRole("heading", { name: "Copies from another source (1)" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "VisitedPage a, source index 3" })).toBeInTheDocument()
    expect(screen.queryByTestId("record-copy")).toBeNull()
  })
})
