/**
 * lx-style data colour (Neil 2 Nov 2026, mock2 "all, build them"): each screen's addition renders, with words beside
 * the colour, and none of it touches the shell. Every test here fails on the code before this change.
 */
import { render, screen, within } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"
import { TooltipProvider } from "@/components/ui/tooltip"
import { SOURCE_TONES, appTone, sourceTone } from "./data-colour"
import { TableGrid } from "@/features/table/components/TableGrid"
import { evidenceKind } from "@/features/evidence/utils/evidence-kind"
import { BalanceMove } from "@/features/financial/components/AccountHistory"
import { dayTotals } from "@/features/financial/components/PaymentCardList"
import { PhoneSummaryProto } from "@/features/phones/prototype/PhoneSummaryProto"
import { TRAINING } from "@/features/phones/fixtures"
import type { LedgerTransaction } from "@/features/financial/api"

vi.mock("@/features/financial/hooks/use-judgement-rows", () => ({ useRowPriority: () => 0 }))

describe("tones", () => {
  it("one stable source colour per account, from the four source tokens", () => {
    expect(sourceTone("acct-1")).toBe(sourceTone("acct-1"))
    const used = new Set(["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"].map((k) => sourceTone(k)))
    for (const tone of used) expect(SOURCE_TONES).toContain(tone)
  })
  it("the four known phone apps each have their own colour", () => {
    const apps = ["WhatsApp", "Telegram", "Signal", "Native Messages"].map((a) => appTone(a).bg)
    expect(new Set(apps).size).toBe(4)
    expect(appTone("whatsapp")).toBe(appTone("WhatsApp"))
  })
})

describe("Financial transactions: day totals", () => {
  const row = (amount: string, direction: "credit" | "debit", currency = "USD") =>
    ({ amount_minor: amount, direction, currency }) as unknown as LedgerTransaction
  it("adds money in and out per currency from exact minor units", () => {
    expect(dayTotals([row("1050", "credit"), row("250", "debit"), row("100", "credit")])).toEqual([
      { currency: "USD", in: "11.50", out: "2.50" },
    ])
  })
  it("gives no total for a currency with an amount that is not whole minor units (never a partial total)", () => {
    const totals = dayTotals([row("10.5", "credit"), row("100", "debit", "EUR")])
    expect(totals.map((t) => t.currency)).toEqual(["EUR"])
  })
})

describe("Trends: balance up / down", () => {
  it("▲ in the money-in colour when the closing is above the opening, ▼ in money-out when below", () => {
    const { container, rerender } = render(<BalanceMove opening="100" closing="250" />)
    const up = container.querySelector("[data-balance-move]") as HTMLElement
    expect(up.dataset.balanceMove).toBe("up")
    expect(up.className).toContain("text-money-in")
    expect(up).toHaveTextContent("▲ rose")
    rerender(<BalanceMove opening="250" closing="100" />)
    const down = container.querySelector("[data-balance-move]") as HTMLElement
    expect(down.className).toContain("text-money-out")
    expect(down).toHaveTextContent("▼ fell")
  })
  it("shows nothing when equal or a balance is missing", () => {
    for (const [o, c] of [["5", "5"], [null, "5"], ["5", undefined]]) {
      const { container, unmount } = render(<BalanceMove opening={o} closing={c} />)
      expect(container.querySelector("[data-balance-move]")).toBeNull()
      unmount()
    }
  })
})

describe("Evidence: what a folder or file holds", () => {
  it("statements from the bank-file check or the name, phone material from the name, documents from the type", () => {
    expect(evidenceKind("anything.pdf", { outcome: "native" } as never)?.kind).toBe("Statements")
    expect(evidenceKind("BANK STATEMENTS 2021")?.kind).toBe("Statements")
    expect(evidenceKind("Phone extraction C5")?.kind).toBe("Phone")
    expect(evidenceKind("interview notes.docx")?.kind).toBe("Document")
    expect(evidenceKind("Misc")).toBeNull()
    expect(evidenceKind("Bankside photos")).toBeNull()
  })
})

describe("Table: type edge, connections bar, sources", () => {
  it("edges each row in its type colour, bars connections against the busiest row, tags sources with words", () => {
    const nodes = [
      { key: "a", label: "Alpha", type: "Person", properties: {} },
      { key: "b", label: "Beta", type: "Location", properties: {} },
    ]
    const columns = [
      { key: "label", label: "Name", fixed: true, sortable: true, defaultVisible: true },
      { key: "connections", label: "Connections", fixed: false, sortable: true, defaultVisible: true },
      { key: "sources", label: "Sources", fixed: false, sortable: true, defaultVisible: true },
    ]
    const { container } = render(
      <TooltipProvider>
        <TableGrid
          pageNodes={nodes as never}
          visibleColumns={columns as never}
          sortColumns={[]}
          onToggleSort={() => {}}
          selectedNodeKey={null}
          onSelectNode={() => {}}
          checkedKeys={new Set()}
          onToggleChecked={() => {}}
          onCheckRange={() => {}}
          onToggleAllChecked={() => {}}
          allChecked={false}
          someChecked={false}
          connectionCounts={new Map([["a", 10], ["b", 5]])}
          sourceCounts={new Map([["a", 2], ["b", 0]])}
          searchTerm=""
          containerRef={{ current: null }}
        />
      </TooltipProvider>
    )
    const edges = [...container.querySelectorAll<HTMLElement>("[data-type-edge]")]
    expect(edges.map((e) => e.dataset.typeEdge)).toEqual(["Person", "Location"])
    expect(edges[0].style.boxShadow).toContain("inset")
    const bars = [...container.querySelectorAll<HTMLElement>("[data-share-bar]")].map((b) => b.dataset.shareBar)
    expect(bars).toEqual(["100", "50"])
    expect(screen.getByText("2 cited")).toBeInTheDocument()
    expect(screen.getByText("no source")).toBeInTheDocument()
  })
})

describe("Phone summary: groups, apps share, coverage gap, top people", () => {
  it("labels each section's group, shows each app's share and colour, marks gap months and bars top people", () => {
    const phone = TRAINING.phones[0].label
    const { container } = render(
      <MemoryRouter>
        <PhoneSummaryProto fx={TRAINING} phone={phone} base="/cases/c/phones-prototype" owners={{}} setOwner={() => {}} />
      </MemoryRouter>
    )
    const groups = [...container.querySelectorAll<HTMLElement>("[data-group]")].map((g) => g.textContent)
    expect(groups).toEqual(["Act", "Activity", "People", "Activity", "Gaps", "Next step"])
    // The group word is decoration: section headings keep their names.
    expect(screen.getByRole("heading", { name: "Needs a decision" })).toBeInTheDocument()
    expect(within(screen.getByTestId("apps-share")).getAllByText("", { selector: "span" }).length).toBeGreaterThan(0)
    expect(container.querySelectorAll("[data-share-bar]").length).toBeGreaterThan(0)
    const gapped = container.querySelectorAll("[data-gap]")
    const noData = screen.queryAllByText(/^No data on \d+ days$/)
    expect(gapped.length).toBe(noData.length)
  })
})
