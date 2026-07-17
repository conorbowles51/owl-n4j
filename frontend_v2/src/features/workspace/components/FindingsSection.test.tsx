import { render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { FindingsSection } from "./FindingsSection"

const workspaceMocks = vi.hoisted(() => ({
  useFindings: vi.fn(),
  useCreateFinding: vi.fn(),
  useUpdateFinding: vi.fn(),
  useDeleteFinding: vi.fn(),
}))

vi.mock("../hooks/use-workspace", () => ({
  useFindings: workspaceMocks.useFindings,
  useCreateFinding: workspaceMocks.useCreateFinding,
  useUpdateFinding: workspaceMocks.useUpdateFinding,
  useDeleteFinding: workspaceMocks.useDeleteFinding,
}))

describe("FindingsSection linked evidence summaries", () => {
  beforeEach(() => {
    workspaceMocks.useCreateFinding.mockReturnValue({ mutate: vi.fn() })
    workspaceMocks.useUpdateFinding.mockReturnValue({ mutate: vi.fn() })
    workspaceMocks.useDeleteFinding.mockReturnValue({ mutate: vi.fn() })
    workspaceMocks.useFindings.mockReturnValue({
      isLoading: false,
      data: [
        {
          id: "finding-1",
          finding_id: "finding-1",
          title: "Funds moved after contact",
          content: "Evidence and entity links should be reviewable.",
          priority: "HIGH",
          linked_evidence_ids: ["file-1", "missing-file"],
          linked_document_ids: ["doc-1"],
          linked_entity_keys: ["entity-1"],
          linked_item_summary: {
            counts: {
              total: 4,
              evidence: 2,
              documents: 1,
              entities: 1,
              resolved: 2,
              missing: 1,
              recycled: 1,
              unverified: 0,
            },
            has_broken_links: true,
            has_recycled_links: true,
            evidence: [
              {
                kind: "evidence",
                id: "file-1",
                requested_id: "file-1",
                title: "bank-report.pdf",
                filename: "bank-report.pdf",
                summary: "Transfers cluster around the suspect account.",
                processing_status: "processed",
                source_open_url: "/api/evidence/file-1/file",
                resolution_status: "resolved",
              },
              {
                kind: "evidence",
                id: "missing-file",
                requested_id: "missing-file",
                title: "missing-file",
                resolution_status: "missing",
              },
            ],
            documents: [
              {
                kind: "document",
                id: "doc-1",
                requested_id: "doc-1",
                title: "warrant-return.pdf",
                filename: "warrant-return.pdf",
                summary: "Return lists the devices seized on March 4.",
                processing_status: "processed",
                source_open_url: "/api/evidence/doc-1/file",
                resolution_status: "resolved",
              },
            ],
            files: [
              {
                kind: "evidence",
                id: "file-1",
                requested_id: "file-1",
                title: "bank-report.pdf",
                filename: "bank-report.pdf",
                summary: "Transfers cluster around the suspect account.",
                processing_status: "processed",
                source_open_url: "/api/evidence/file-1/file",
                resolution_status: "resolved",
              },
              {
                kind: "evidence",
                id: "missing-file",
                requested_id: "missing-file",
                title: "missing-file",
                resolution_status: "missing",
              },
              {
                kind: "document",
                id: "doc-1",
                requested_id: "doc-1",
                title: "warrant-return.pdf",
                filename: "warrant-return.pdf",
                summary: "Return lists the devices seized on March 4.",
                processing_status: "processed",
                source_open_url: "/api/evidence/doc-1/file",
                resolution_status: "resolved",
              },
            ],
            entities: [
              {
                kind: "entity",
                id: "entity-1",
                requested_id: "entity-1",
                title: "Archived Person",
                recycle_key: "recycled_entity-1",
                resolution_status: "recycled",
              },
            ],
          },
        },
      ],
    })
  })

  it("shows broken and recycled counts with linked file summaries", () => {
    render(<FindingsSection caseId="case-1" />)

    expect(screen.getByText("4 linked items")).toBeInTheDocument()
    expect(screen.getByText("1 broken")).toBeInTheDocument()
    expect(screen.getByText("1 recycled")).toBeInTheDocument()
    expect(screen.getByText("Transfers cluster around the suspect account.")).toBeInTheDocument()
    expect(screen.getByText("Return lists the devices seized on March 4.")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "bank-report.pdf" })).toHaveAttribute(
      "href",
      "/api/evidence/file-1/file",
    )
  })
})
