import { describe, expect, it } from "vitest"
import {
  nearbyPayments,
  paymentDay,
  paymentPeriods,
  paymentProfiles,
  profileAccountGroup,
  chartRatio,
} from "./investigator-workspace"
import {
  findingBody,
  findingDraft,
  findingTags,
  emptyFinding,
} from "./investigator-finding"
import { paymentFixture } from "./payment-fixture.test-support"
import type { LedgerTransaction } from "../api"
import type { CaseworkEntry } from "@/features/workspace/casework-api"

const row = (
  key: string,
  date: string,
  direction: string,
  account = "a",
  currency = "EUR"
): LedgerTransaction => ({
  ...paymentFixture,
  key,
  account_id: account,
  direction,
  currency,
  ordering_date: date,
  amount_minor: "12500000",
  ledger_status: "admitted",
})

describe("investigator comparisons and charts", () => {
  it("does not invent an account-type filter for registered accounts with unknown type", () => {
    expect(
      profileAccountGroup({ currency: "EUR", accountType: null })
    ).toBeNull()
    expect(
      profileAccountGroup({ currency: null, accountType: "checking" })
    ).toBeNull()
    expect(
      profileAccountGroup({ currency: "EUR", accountType: "checking" })
    ).toBe("EUR:bank")
    expect(
      profileAccountGroup({ currency: "EUR", accountType: "credit_card" })
    ).toBe("EUR:card")
  })
  it("uses suggested names in profiles but respects an explicit cleared name", () => {
    const suggested = {
      ...row("suggested", "2023-03-18", "debit"),
      to_name: "Nike",
      category: "Shopping",
      counterparty_raw: "Older reading",
    }
    const groups = paymentProfiles([
      suggested,
      { ...suggested, key: "cleared", to_name: "" },
    ])
    expect(groups.find((group) => group.id === "name:Nike")?.rows).toHaveLength(
      1
    )
    expect(groups.some((group) => group.name === "Older reading")).toBe(false)
    expect(groups.find((group) => group.id === "name:")?.rows[0].key).toBe(
      "cleared"
    )
  })
  it("compares adjacent dated bank payments within the same account and currency", () => {
    const incoming = row("in", "2023-03-18", "credit")
    const outgoing = {
      ...row("out", "2023-03-20", "debit"),
      amount_minor: "12000000",
    }
    const noise = [
      row("other-account", "2023-03-19", "debit", "b"),
      row("other-currency", "2023-03-19", "debit", "a", "USD"),
      {
        ...row("unknown-date", "2023-03-19", "debit"),
        ordering_date_context: "statement_end_ordering_only" as const,
      },
    ]
    const pairs = nearbyPayments([outgoing, ...noise, incoming])
    expect(pairs).toHaveLength(1)
    expect(pairs[0]).toMatchObject({
      incoming,
      outgoing,
      days: 2,
      difference: 500000n,
    })
    expect(nearbyPayments([incoming, outgoing], 1)).toEqual([])
    expect(
      nearbyPayments([
        { ...incoming, account_type: "credit_card" },
        { ...outgoing, account_type: "credit_card" },
      ])
    ).toEqual([])
  })
  it("shows represented monthly payments only, preserving exact large amounts", () => {
    const periods = paymentPeriods(
      [
        {
          ...row("large", "2023-03-18", "credit"),
          amount_minor: "9007199254740993",
        },
      ],
      "month",
      "2023-01-01",
      "2023-12-31"
    )
    expect(periods).toHaveLength(1)
    expect(periods[0]).toMatchObject({
      date: "2023-03-01",
      end: "2023-03-31",
      credit: 9007199254740993n,
    })
    expect(chartRatio(9007199254740993n, 9007199254740993n)).toBe(1)
  })
  it("does not chart invalid dates or statement-end substitutes and flags unreadable amounts", () => {
    expect(paymentDay(row("bad", "2023-02-29", "credit"))).toBe(null)
    expect(
      paymentDay({
        ...row("unknown", "2023-03-31", "credit"),
        ordering_date_context: "statement_end_ordering_only",
      })
    ).toBe(null)
    const periods = paymentPeriods(
      [
        {
          ...row("unsafe", "2024-02-29", "credit"),
          amount_minor: Number.MAX_SAFE_INTEGER + 1,
        },
      ],
      "day",
      "2024-02-28",
      "2024-03-01"
    )
    expect(periods).toHaveLength(3)
    expect(periods[1]).toMatchObject({ credit: 0n, unreadable: 1 })
  })
  it("keeps different printed names separate and dates unknown where necessary", () => {
    const profiles = paymentProfiles([
      {
        ...row("one", "2023-01-01", "credit"),
        counterparty_raw: "Example Ltd",
      },
      {
        ...row("two", "2023-01-01", "credit"),
        counterparty_raw: "EXAMPLE LTD",
      },
      {
        ...row("three", "2023-01-01", "debit"),
        counterparty_raw: null,
        ordering_date_context: "statement_end_ordering_only",
      },
    ])
    expect(profiles.filter((profile) => profile.kind === "name")).toHaveLength(
      3
    )
    expect(
      profiles.find((profile) => profile.name === "Name not recorded")
    ).toMatchObject({ first: null, last: null })
    expect(
      profiles.find((profile) => profile.kind === "account")?.rows
    ).toHaveLength(3)
  })
  it("preserves finding text including literal section headings across edits", () => {
    const draft = {
      ...emptyFinding,
      title: "Question",
      explanation:
        "Check this.\n\n## Next action\nLiteral explanation heading\n\\## Assigned to\nLiteral",
      nextAction: "Obtain records.\n## Assigned to\nIn quoted text",
      owner: "Alex",
      progress: "in-progress" as const,
    }
    const entry = {
      title: draft.title,
      body: findingBody(draft),
      tags: findingTags(draft),
      links: [],
    } as unknown as CaseworkEntry
    expect(findingDraft(entry)).toEqual(draft)
    expect(
      findingTags(
        { ...draft, kind: "conclusion", progress: "complete" },
        entry.tags
      )
    ).not.toContain("financial-question")
    expect(
      findingTags(
        { ...draft, kind: "conclusion", progress: "complete" },
        entry.tags
      )
    ).not.toContain("financial-in-progress")
  })
  it.each([
    { nextAction: "", owner: "" },
    { nextAction: "Compare the original records.", owner: "" },
    { nextAction: "", owner: "Investigator" },
  ])(
    "reopens trimmed optional sections without leaking storage headings: %j",
    (optional) => {
      const draft = {
        ...emptyFinding,
        title: "Source review",
        explanation: "## Evidence\nThe payment needs review.",
        ...optional,
      }
      for (const newline of ["\n", "\r\n"]) {
        const body = findingBody(draft).trimEnd().replace(/\n/g, newline)
        const entry = {
          title: draft.title,
          tags: findingTags(draft),
          body,
          links: [],
        } as unknown as CaseworkEntry
        expect(findingDraft(entry)).toEqual(draft)
        expect(entry.body).toBe(body)
      }
    }
  )
})

it("separates a confirmed holder's five accounts from appearances on outsiders' accounts", () => {
  const party = { id: "person", name: "Example Holder" }
  const directory = Array.from({ length: 5 }, (_, n) => ({
    id: `a${n}`,
    canonical_id: `a${n}`,
    institution: "Example Bank",
    identifier_as_printed: `000${n}`,
    currency: n === 4 ? "USD" : "EUR",
    holder_as_recorded: party.name,
    party: null,
    relationships: [],
    holder_parties: [party],
  }))
  const owned = {
    ...row("own", "2026-01-05", "debit", "a0"),
    account_holder_parties: [party],
  }
  const incoming = {
    ...row("outside", "2026-01-06", "debit", "outsider"),
    to_name: party.name,
    counterparty_link: {
      kind: "party" as const,
      id: party.id,
      label: party.name,
    },
  }
  const profiles = paymentProfiles([owned, owned, incoming], directory)
  const owner = profiles.find((p) => p.id === "owner:person")!
  expect(owner.rows.map((r) => r.key)).toEqual(["own"])
  expect(owner.counterpartyRows.map((r) => r.key)).toEqual(["outside"])
  expect(owner.accounts).toEqual(["a0", "a1", "a2", "a3", "a4"])
  expect(
    profiles.filter((p) => p.kind === "account" && p.nestedUnderOwner)
  ).toHaveLength(5)
  expect(profiles.find((p) => p.id === "account:a4")?.rows).toHaveLength(0)
})
it("limits owned activity to confirmed holder dates without losing historical account relationships", () => {
  const party = { id: "person", name: "Example Holder" }
  const linked = {
    ...row("before", "2025-01-01", "credit"),
    account_holder_parties: [party],
    account_relationships: [
      {
        id: "link",
        party,
        role: "holder" as const,
        basis: "investigator_knowledge" as const,
        sources: [],
        effective_from: "2026-01-01",
        effective_to: "2026-12-31",
      },
    ],
  }
  const profiles = paymentProfiles([
    linked,
    { ...linked, key: "during", ordering_date: "2026-02-01" },
    {
      ...linked,
      key: "undated",
      ordering_date_context: "statement_end_ordering_only",
    },
  ])
  expect(
    profiles.find((p) => p.id === "owner:person")?.rows.map((r) => r.key)
  ).toEqual(["during"])
  expect(profiles.find((p) => p.id === "owner:person")?.accounts).toEqual(["a"])
})

it("retains quiet statement metadata and canonical account fields across an empty alias without inventing payments", () => {
  const holder = { id: "person", name: "Confirmed Holder" }
  const source = "quiet-source"
  const directory = [
    {
      id: "canonical",
      canonical_id: "canonical",
      institution: "Example Bank",
      identifier_as_printed: "000123",
      currency: "EUR",
      account_type: "checking",
      holder_as_recorded: holder.name,
      party: null,
      relationships: [],
      holder_parties: [holder],
      statement_periods: [
        {
          id: "jan",
          source_document_id: source,
          start: "2026-01-01",
          end: "2026-01-31",
        },
      ],
    },
    {
      id: "alias",
      canonical_id: "canonical",
      institution: null,
      identifier_as_printed: null,
      currency: null,
      account_type: null,
      holder_as_recorded: null,
      party: null,
      relationships: [],
      holder_parties: [holder],
      statement_periods: [
        {
          id: "feb",
          source_document_id: source,
          start: "2026-02-01",
          end: "2026-02-28",
        },
      ],
    },
  ]
  const profiles = paymentProfiles([], directory)
  const quiet = profiles.find((profile) => profile.id === "account:canonical")!
  expect(quiet.rows).toEqual([])
  expect(quiet.first).toBeNull()
  expect(quiet.last).toBeNull()
  expect(quiet.statementFirst).toBe("2026-01-01")
  expect(quiet.statementLast).toBe("2026-02-28")
  expect(quiet.sources).toEqual([source])
  expect(quiet.statementPeriods).toHaveLength(2)
  expect(quiet.accountDetails).toEqual([
    expect.objectContaining({
      institution: "Example Bank",
      number: "000123",
      currency: "EUR",
      accountType: "checking",
      registered: true,
    }),
  ])
  const owner = profiles.find((profile) => profile.id === "owner:person")!
  expect(owner.accounts).toEqual(["canonical"])
  expect(owner.statementPeriods).toHaveLength(2)
  expect(owner.rows).toEqual([])
  const linked = paymentProfiles(
    [
      {
        ...row("outside", "2026-03-01", "debit", "another"),
        counterparty_link: { kind: "account", id: "alias", label: "old alias" },
      },
    ],
    directory
  )
  expect(linked.some((profile) => profile.id === "account:alias")).toBe(false)
  expect(
    linked
      .find((profile) => profile.id === "account:canonical")
      ?.counterpartyRows.map((r) => r.key)
  ).toEqual(["outside"])
})

it("keeps an unresolved linked account as a labelled reference without borrowing the paying account's currency or dates", () => {
  const profiles = paymentProfiles([
    {
      ...row("outside", "2026-01-01", "debit", "paying-account"),
      counterparty_link: {
        kind: "account",
        id: "legacy-reference",
        label: "Unresolved account reference",
      },
    },
  ])
  const unresolved = profiles.find(
    (profile) => profile.id === "account:legacy-reference"
  )!
  expect(unresolved.accounts).toEqual(["legacy-reference"])
  expect(unresolved.accountDetails[0]).toMatchObject({
    registered: false,
    currency: null,
    institution: null,
    number: null,
  })
  expect(unresolved.sources).toEqual([])
  expect(unresolved.statementPeriods).toEqual([])
  expect(unresolved.first).toBeNull()
  expect(unresolved.counterpartyRows).toHaveLength(1)
})
