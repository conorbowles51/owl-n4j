import { render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { describe, expect, it, vi } from "vitest"

/** 07 CO-9a and CO-9b on a link: from a replaced copy, with the matching record offered or the reason none is. Invented data only. */
const fetchAPI = vi.hoisted(() => vi.fn())
vi.mock("@/lib/api-client", () => ({ fetchAPI }))

import { ReplacedLinkNote } from "./ReplacedLinkNote"
import { replacedLinks, useReplacedLinks } from "./replaced-links"

const LINKS = [
  { target_type: "phone_record", target_id: "u-old" },
  { target_type: "phone_record", target_id: "u-gone" },
  { target_type: "phone_record", target_id: "u-current" },
  { target_type: "evidence", target_id: "e1" },
]

function Harness() {
  const replaced = useReplacedLinks("c1", LINKS)
  return <ul>{LINKS.map((l) => <li key={l.target_id} data-testid={l.target_id}><ReplacedLinkNote caseId="c1" state={replaced[l.target_id]} /></li>)}</ul>
}

describe("A link to a record of a replaced report (CO-9a, CO-9b)", () => {
  it("says it is from a replaced copy and offers the matching record, or says why none is offered", async () => {
    fetchAPI.mockReset().mockResolvedValue({ items: {
      "u-old": { replaced: true, words: "From a replaced copy. The report that replaced it holds the same record.", newer_extraction_id: "x2", newer_record_uid: "u-new", newer_record_type: "InstantMessage" },
      "u-gone": { replaced: true, words: "From a replaced copy. The report that replaced it holds no record with the same content, time and people, so none is offered.", newer_extraction_id: null, newer_record_uid: null, newer_record_type: null },
      "u-current": { replaced: false, words: null, newer_extraction_id: null, newer_record_uid: null, newer_record_type: null },
    } })
    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter><Harness /></MemoryRouter></QueryClientProvider>)
    const offered = await screen.findByRole("link", { name: "Open the matching record" })
    expect(offered).toHaveAttribute("href", "/cases/c1/records/u-new")
    expect(screen.getByTestId("u-old")).toHaveTextContent("From a replaced copy. The report that replaced it holds the same record.")
    expect(screen.getByTestId("u-gone")).toHaveTextContent("holds no record with the same content, time and people, so none is offered.")
    expect(screen.getByTestId("u-gone").querySelector("a")).toBeNull()
    expect(screen.getByTestId("u-current")).toBeEmptyDOMElement()
    expect(fetchAPI).toHaveBeenCalledTimes(1)
    expect(fetchAPI.mock.calls[0][1].body.record_uids).toEqual(["u-current", "u-gone", "u-old"])
  })

  it("asks in batches so no link is left out", async () => {
    fetchAPI.mockReset().mockImplementation((_u: string, o: { body: { record_uids: string[] } }) =>
      Promise.resolve({ items: Object.fromEntries(o.body.record_uids.map((u) => [u, { replaced: false }])) }))
    const uids = Array.from({ length: 1001 }, (_, i) => `u${i}`)
    const out = await replacedLinks("c1", uids)
    expect(fetchAPI).toHaveBeenCalledTimes(3)
    expect(Object.keys(out)).toHaveLength(1001)
  })
})
