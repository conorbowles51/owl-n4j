import { render, screen } from "@testing-library/react"
import { expect, it } from "vitest"
import { AgentArtifactNotes } from "./AgentArtifactNotes"
import type { AgentArtifact } from "../types"

const artifact: AgentArtifact = {
  id: "synthetic",
  type: "table",
  title: "Imported payments",
  data: {},
  metadata: {},
}

it("shows stored table coverage and preserves different chart notes without duplicate text", () => {
  const notes =
    "Working population: 2 of 130 supporting rows shown. EUR bank and USD card totals are separate. January and March represented; February unknown."
  const view = render(
    <AgentArtifactNotes artifact={{ ...artifact, metadata: { notes } }} />
  )
  expect(
    screen.getByRole("region", { name: "Analysis scope and notes" })
  ).toHaveTextContent(notes)
  view.rerender(
    <AgentArtifactNotes
      artifact={{
        ...artifact,
        type: "chart",
        data: { notes },
        metadata: { notes },
      }}
    />
  )
  expect(screen.getAllByText(notes)).toHaveLength(1)
  view.rerender(
    <AgentArtifactNotes
      artifact={{
        ...artifact,
        type: "chart",
        data: { notes },
        metadata: {
          notes: "Snapshot changed; refresh before relying on comparisons.",
        },
      }}
    />
  )
  expect(screen.getByRole("region")).toHaveTextContent("Snapshot changed")
  expect(screen.getByRole("region")).toHaveTextContent(notes)
})

it("renders notes as text and makes no coverage claim when notes are absent", () => {
  const view = render(<AgentArtifactNotes artifact={artifact} />)
  expect(screen.queryByRole("region")).toBeNull()
  view.rerender(
    <AgentArtifactNotes
      artifact={{
        ...artifact,
        metadata: { notes: '<img src="x" onerror="alert(1)">Coverage unknown' },
      }}
    />
  )
  expect(screen.getByRole("region")).toHaveTextContent("Coverage unknown")
  expect(view.container.querySelector("img")).toBeNull()
  expect(screen.getByRole("region")).toHaveAttribute("tabindex", "0")
})
