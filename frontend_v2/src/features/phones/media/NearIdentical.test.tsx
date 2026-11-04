import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"

/** 05 11.8 test 4 on screen and the thin-data line (cb-gated-spread E). Invented data only. */
const copy = (over: object) => ({ file_uid: "f1", extraction_id: "e1", phone_label: "C1", md5: "a".repeat(32), filename: "synthetic-a.jpg", category: "Image", copies_on_phone: 1, roles: ["sent"], messages_total: 0, messages: [], ...over })
const page = {
  case_id: "c1", tier: "perceptual", total: 1, offset: 0, limit: 50, total_all: 1, pictures_compared: 5, stopped_words: null,
  by_strength: { strong: 0, moderate: 1, weak: 0, faint: 0 }, words: "Pictures that look nearly the same on two phones although the files differ.",
  rule_words: "These levels are rules of thumb, not measured on this case.", clock_words: "Times are each phone's own clock.",
  hashing: { pictures: 6, hashed: 5, failed: 1, waiting: 0, failed_by_reason: { cannot_open: 1 }, failed_words: { cannot_open: "could not be opened." }, case_phones: 2, not_hashed_words: null },
  items: [{ level: "moderate", distance: 3, phash_distance: 3, dhash_distance: 2, simple: false, label: "Lead for enquiry",
    reasons: { match: ["3 of 64 bits differ in the picture hash and 2 in the edge hash; moderate by the rule."], substantiation: ["Copies on each phone: 1 and 1."] },
    a: copy({}), b: copy({ file_uid: "f2", extraction_id: "e2", phone_label: "C2", md5: "b".repeat(32), filename: "synthetic-a-recompressed.jpg", roles: ["received"] }) }],
}
const api = vi.hoisted(() => ({ getMediaSpreadPerceptual: vi.fn() }))
vi.mock("../api", async (orig) => ({ ...(await orig<object>()), ...api }))
import { NearIdentical } from "./NearIdentical"

describe("Near-identical pictures (05 11.3 step 3)", () => {
  it("lists the pair with its strength, the counts by strength and the hashing counts", async () => {
    api.getMediaSpreadPerceptual.mockResolvedValue(page)
    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter><NearIdentical caseId="c1" onOpen={() => {}} /></MemoryRouter></QueryClientProvider>)
    const pair = await screen.findByTestId("near-identical-pair")
    expect(pair).toHaveTextContent("Lead for enquiry")
    expect(pair).toHaveTextContent("Moderate: 3 of 64 bits differ")
    expect(pair).toHaveTextContent("C1: Open synthetic-a.jpg; sent")
    expect(pair).toHaveTextContent("C2: Open synthetic-a-recompressed.jpg; received")
    expect(screen.getByTestId("near-identical-counts")).toHaveTextContent("1 near-identical pair in all: strong 0, moderate 1, weak 0, faint 0.")
    expect(screen.getByTestId("near-identical-thin")).toHaveTextContent("5 of 6 pictures compared; 1 could not be read")
    expect(screen.getByText(/rules of thumb/)).toBeInTheDocument()
    expect(document.body.textContent).not.toMatch(/identical file|—/)
  })
})
