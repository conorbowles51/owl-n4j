import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import type { CaseworkEntryType } from "../casework-api"
import { CaseworkComposer } from "./CaseworkComposer"

vi.mock("./CaseworkAttachmentPicker", () => ({
  CaseworkAttachmentPicker: ({ onAttach }: { onAttach: (link: unknown) => void }) => (
    <button
      type="button"
      onClick={() =>
        onAttach({
          target_type: "evidence",
          target_id: "evidence-browser-1",
          target_label: "Statement.pdf",
          relationship: "unclassified",
          source_anchor: { page: 9 },
          metadata: {},
        })
      }
    >
      Attach browser evidence
    </button>
  ),
}))

describe("unified casework composer in Chromium", () => {
  for (const type of ["note", "finding", "theory"] as CaseworkEntryType[]) {
    it(`creates a ${type} with the shared interaction language`, async () => {
      const onSubmit = vi.fn()
      render(
        <CaseworkComposer
          caseId="case-browser"
          initialType={type}
          currentSelection={[
            {
              target_type: "graph_entity",
              target_id: "person-browser-1",
              target_label: "Henry Walsh",
              relationship: "unclassified",
              source_anchor: {},
              metadata: { source: "current_selection" },
            },
          ]}
          onSubmit={onSubmit}
        />,
      )

      if (type !== "note") {
        fireEvent.change(screen.getByLabelText(/^Title/), {
          target: { value: `${type} browser title` },
        })
      }
      fireEvent.change(screen.getByLabelText("Casework"), {
        target: { value: `Browser-authored ${type} body` },
      })
      fireEvent.click(screen.getByRole("button", { name: /Attach selection/ }))
      fireEvent.click(screen.getByRole("button", { name: "Search" }))
      fireEvent.click(screen.getByRole("button", { name: "Attach browser evidence" }))
      fireEvent.click(
        screen.getByRole("button", { name: `Save ${type}` }),
      )

      await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1))
      expect(onSubmit.mock.calls[0][0]).toMatchObject({
        entry_type: type,
        body: `Browser-authored ${type} body`,
        links: [
          { target_type: "graph_entity", target_label: "Henry Walsh" },
          {
            target_type: "evidence",
            target_label: "Statement.pdf",
            source_anchor: { page: 9 },
          },
        ],
      })
    })
  }
})
