import { fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { Table, TableBody } from "@/components/ui/table"
import { TooltipProvider } from "@/components/ui/tooltip"
import type { EvidenceFileRecord } from "@/types/evidence.types"
import { FileRow } from "./FileRow"

const mocks = vi.hoisted(() => ({
  openDetail: vi.fn(),
  toggle: vi.fn(),
  process: vi.fn(),
}))

vi.mock("../evidence.store", () => ({
  useEvidenceStore: () => ({
    selectedFileIds: new Set<string>(),
    toggleFileSelection: mocks.toggle,
    openDetail: mocks.openDetail,
  }),
}))

vi.mock("../hooks/use-guarded-process", () => ({
  useGuardedProcess: () => ({ start: mocks.process, isChecking: false, isProcessing: false, held: null }),
}))
vi.mock("./ProcessHoldDialog", () => ({ ProcessHoldDialog: () => null }))

const file = {
  id: "evidence-1",
  case_id: "case-1",
  folder_id: null,
  original_filename: "bank-statement.pdf",
  stored_path: "/fixtures/bank-statement.pdf",
  size: 2048,
  sha256: "a".repeat(64),
  status: "processed",
  processing_stale: false,
  is_duplicate: false,
  duplicate_of: null,
  is_relevant: true,
  owner: null,
  entity_count: 4,
  relationship_count: 2,
  created_at: "2026-09-01T12:00:00Z",
  processed_at: "2026-09-01T12:05:00Z",
  last_error: null,
  legacy_id: null,
  summary: null,
  transcription: null,
  transcription_segments: [],
  transcription_speakers: {},
  transcription_speaker_merges: {},
  last_processed_folder_id: null,
} satisfies EvidenceFileRecord

function renderRow(props: Partial<React.ComponentProps<typeof FileRow>> = {}) {
  return render(
    <TooltipProvider>
      <Table>
        <TableBody>
          <FileRow file={file} caseId="case-1" {...props} />
        </TableBody>
      </Table>
    </TooltipProvider>,
  )
}

describe("FileRow workspace pin actions", () => {
  beforeEach(() => {
    mocks.openDetail.mockReset()
    mocks.toggle.mockReset()
    mocks.process.mockReset()
  })

  it("offers an individual pin action for unpinned evidence", async () => {
    const onPin = vi.fn()
    renderRow({ isPinned: false, onPin })
    fireEvent.pointerDown(
      screen.getByRole("button", { name: "Actions for bank-statement.pdf" }),
      { button: 0, ctrlKey: false },
    )
    fireEvent.click(await screen.findByText("Pin to workspace"))

    expect(onPin).toHaveBeenCalledWith("evidence-1")
  })

  it("shows the already-pinned state and unpins by shared pin identity", async () => {
    const onUnpin = vi.fn()
    renderRow({ isPinned: true, pinId: "pin-1", onUnpin })
    fireEvent.pointerDown(
      screen.getByRole("button", { name: "Actions for bank-statement.pdf" }),
      { button: 0, ctrlKey: false },
    )
    fireEvent.click(await screen.findByText("Unpin from workspace"))

    expect(onUnpin).toHaveBeenCalledWith("pin-1")
    expect(screen.queryByText("Pin to workspace")).not.toBeInTheDocument()
  })

  it("renders no pin mutation when the caller is read-only", async () => {
    renderRow({ isPinned: false })
    fireEvent.pointerDown(
      screen.getByRole("button", { name: "Actions for bank-statement.pdf" }),
      { button: 0, ctrlKey: false },
    )

    expect(screen.queryByText("Pin to workspace")).not.toBeInTheDocument()
    expect(screen.queryByText("Unpin from workspace")).not.toBeInTheDocument()
  })
})
