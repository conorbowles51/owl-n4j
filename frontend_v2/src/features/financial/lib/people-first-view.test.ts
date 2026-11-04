/**
 * The People & businesses list from the server equals the browser's own grouping of the same payments.
 *
 * `people-parity.fixture.json` holds payments and an account directory made to reach every rule (an alias joined
 * into its account with periods and links merged, holders with dated, open and absent relationships, a joint
 * account, a directory-only account, a counterparty linked to a person and to an account by its alias, names with
 * spaces, blank, missing and raw names, every kind of unnamed payment in both directions, undated, statement-end-only
 * and impossible dates, unreadable and negative amounts, a card and other currencies) and the server's answers for
 * several choices of currency and category. The backend test (test_financial_people_first_view.py) checks the
 * server still gives those answers; this one checks the browser's grouping gives the same cards. The equality over
 * the six live cases is a gate run outside the suite.
 */
import { describe, expect, it } from "vitest"
import type { LedgerTransaction } from "../api"
import fixture from "./people-parity.fixture.json"
import { accountParties } from "./account-parties"
import { paymentGroup, paymentProfiles, profileAccountGroup } from "./investigator-workspace"
import { matchesCategories } from "../hooks/use-payment-categories"
import { profileCard, serverProfileCards, type ProfileCard, type ServerProfile } from "./people-first-view"

const comparable = (card: ProfileCard) => ({
  ...card,
  amount: String(card.amount),
  totals: card.totals && {
    payments: card.totals.payments,
    unreadable: card.totals.unreadable,
    inventory: {
      ...card.totals.inventory,
      accounts: card.totals.inventory.accounts.map((a) => [a.id, a.label, [...a.currencies].sort()]),
    },
    totals: [...card.totals.totals].map(([group, t]) => [group, String(t.credit), String(t.debit), t.count, t.accountCount]),
  },
})

describe("people list from the server", () => {
  const rows = fixture.rows as unknown as LedgerTransaction[]
  const directory = accountParties.parse(fixture.directory)

  it("covers the rules it is meant to", () => {
    const all = fixture.scenarios[0].server as unknown as { profiles: ServerProfile[] }
    const kinds = new Set(all.profiles.map((p) => p.kind))
    expect([...kinds].sort()).toEqual(["account", "name", "owner"])
    expect(all.profiles.filter((p) => p.unidentified).length).toBe(2)
    expect(all.profiles.some((p) => p.counterparty_payments > 0 && p.kind === "owner")).toBe(true)
    expect(all.profiles.some((p) => p.totals?.unreadable)).toBe(true)
    expect(all.profiles.some((p) => p.account_details.some((a) => !a.coverage))).toBe(true)
  })

  for (const scenario of fixture.scenarios) {
    it(`gives the browser's cards for ${JSON.stringify(scenario.ask)}`, () => {
      const ask = scenario.ask as { group?: string; categories?: string[] }
      const server = scenario.server as unknown as {
        row_count: number
        row_groups: string[]
        directory_groups: string[]
        profiles: ServerProfile[]
      }
      const chosen = rows.filter((row) => matchesCategories(row, ask.categories ?? []))
      const scoped = chosen.filter((row) => !ask.group || paymentGroup(row) === ask.group)
      expect(server.row_count).toBe(chosen.length)
      expect(server.row_groups).toEqual([...new Set(chosen.map(paymentGroup))])
      expect(server.directory_groups).toEqual([
        ...new Set(
          directory.accounts.flatMap((account) => {
            const group = profileAccountGroup({ currency: account.currency, accountType: account.account_type || null })
            return group ? [group] : []
          })
        ),
      ])
      const browser = paymentProfiles(scoped, directory.accounts).map(profileCard).map(comparable)
      expect(serverProfileCards(server.profiles).map(comparable)).toEqual(browser)
    })
  }
})
