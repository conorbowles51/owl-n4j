import { render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { describe, expect, it, vi } from "vitest"

/** 05 section 5.4 in Conversations: the badge per message from Messages across phones. Invented data only. */
const fetchAPI = vi.hoisted(() => vi.fn())
vi.mock("@/lib/api-client", () => ({ fetchAPI }))

import { AcrossBadges, AcrossBadgesSource } from "./AcrossBadges"
import { loadedChunks, useAcrossBadges } from "./across-badges"
import type { StreamItem } from "./hooks/use-stream"

const row = (uid: string, copies: string[] = []) => ({ record_uid: uid, copies: { count: copies.length + 1, record_uids: copies, apps: [] } }) as never
const item = (r: unknown, windowKey = "w"): StreamItem => ({ type: "row", segment: 0, offset: 0, row: r as never, state: r ? "loaded" : "loading", windowKey })

describe("Messages across phones badges in Conversations (05 5.4)", () => {
  it("asks for each loading window once its rows have arrived, copies included, never a part of one", () => {
    const items: StreamItem[] = [{ type: "header", segment: 0 }, item(row("u1", ["u1b"]), "0|0"), item(row("u2"), "0|0"),
      item(null, "0|100"), item(null, "0|100"), item(row("v1"), "1|0")]
    const chunks = loadedChunks({ count: items.length, item: (i) => items[i] })
    expect(chunks).toEqual([["u1", "u1b", "u2"], ["v1"]])   // the window still loading is not asked yet
  })

  it("shows a row's badges, the reasons and the other copy, and says where they come from", async () => {
    fetchAPI.mockReset().mockResolvedValue({ run: { id: "r1", finished_at: "2026-11-03T10:00:00Z", current: false }, items: {
      u1b: [{ kind: "both_sides", other_phone: "C2", other_record_uid: "w1", tier: "matched_strong", words: "Also on C2", reasons: [], result_id: "x" }],
      u2: [{ kind: "one_side_only", other_phone: "C2", other_record_uid: null, tier: null, words: "Only on this phone, not on C2", reasons: ["C2 was extracted before this message."], result_id: "y" }],
    } })
    const items: StreamItem[] = [item(row("u1", ["u1b"])), item(row("u2")), item(row("u3"))]
    function Harness() {
      const across = useAcrossBadges("c1", { count: items.length, item: (i) => items[i] })
      return (
        <div>
          <AcrossBadgesSource run={across.run} />
          {items.map((it) => it.type === "row" && it.row && (
            <div key={(it.row as { record_uid: string }).record_uid} data-testid={(it.row as { record_uid: string }).record_uid}>
              <AcrossBadges caseId="c1" badges={across.forRow(it.row)} />
            </div>))}
        </div>)
    }
    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter><Harness /></MemoryRouter></QueryClientProvider>)
    expect(await screen.findByText("Also on C2")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Open the copy on C2" })).toHaveAttribute("href", "/cases/c1/records/w1")
    expect(screen.getByTestId("u2")).toHaveTextContent("Only on this phone, not on C2 (C2 was extracted before this message.)")
    expect(screen.getByTestId("u3")).toBeEmptyDOMElement()
    expect(screen.getByTestId("across-badges-source")).toHaveTextContent("a message it did not compare has no badge")
    expect(screen.getByTestId("across-badges-source")).toHaveTextContent("The phones have changed since that run")
    expect(fetchAPI.mock.calls[0][1].body.record_uids).toEqual(["u1", "u1b", "u2", "u3"])
  })
})
