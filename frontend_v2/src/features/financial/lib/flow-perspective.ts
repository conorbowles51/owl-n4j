import type { TransferInputs } from "./ledger-transfers"
export function accountPerspective(
  scope: TransferInputs,
  selectedAccounts: string[],
  pairs: { debit_id: string; credit_id: string }[]
) {
  const selected = new Set(selectedAccounts),
    rows = new Map(scope.rows.map((r) => [r.key, r])),
    used = new Set<string>()
  if (
    selected.size !== selectedAccounts.length ||
    selectedAccounts.some((id) => !scope.rows.some((r) => r.account_id === id))
  )
    throw Error("Choose distinct accounts in the captured scope.")
  const movements: {
    kind: "incoming" | "outgoing" | "internal"
    currency: string
    amount_minor: string
    transaction_ids: string[]
    label: string
    group_id: string
  }[] = []
  for (const pair of pairs) {
    if (
      !scope.candidates.some(
        (p) => p.debit_id === pair.debit_id && p.credit_id === pair.credit_id
      ) ||
      used.has(pair.debit_id) ||
      used.has(pair.credit_id)
    )
      throw Error("Invalid or reused transfer pairing.")
    used.add(pair.debit_id)
    used.add(pair.credit_id)
    const d = rows.get(pair.debit_id)!,
      c = rows.get(pair.credit_id)!,
      out = selected.has(d.account_id),
      into = selected.has(c.account_id)
    if (!out && !into) continue
    const kind = out && into ? "internal" : out ? "outgoing" : "incoming",
      other = out ? c : d
    movements.push({
      kind,
      currency: d.currency,
      amount_minor: d.amount_minor,
      transaction_ids: [d.key, c.key],
      label:
        kind === "internal"
          ? "Within selected accounts"
          : (other.account_label ?? "Account " + other.account_id.slice(0, 8)),
      group_id: "account:" + other.account_id,
    })
  }
  for (const row of scope.rows) {
    if (used.has(row.key) || !selected.has(row.account_id)) continue
    const label = row.counterparty_raw
      ? `${row.account_label ?? "Account " + row.account_id.slice(0, 8)} · unpaired source label: ${row.counterparty_raw}`
      : `${row.account_label ?? "Account " + row.account_id.slice(0, 8)} · unpaired posting; other account unknown`
    movements.push({
      kind: row.direction === "credit" ? "incoming" : "outgoing",
      currency: row.currency,
      amount_minor: row.amount_minor,
      transaction_ids: [row.key],
      label,
      group_id: JSON.stringify([
        "unpaired",
        row.account_id,
        row.counterparty_raw ?? null,
      ]),
    })
  }
  const currencies = [...new Set(movements.map((m) => m.currency))].sort()
  const totals = currencies.map((currency) => {
    const scoped = movements.filter((m) => m.currency === currency),
      sum = (kind: string) =>
        scoped
          .filter((m) => m.kind === kind)
          .reduce((n, m) => n + BigInt(m.amount_minor), 0n)
    const incoming = sum("incoming"),
      outgoing = sum("outgoing"),
      internal = sum("internal")
    const rawNet = scope.rows
      .filter((r) => r.currency === currency && selected.has(r.account_id))
      .reduce(
        (n, r) =>
          n + (r.direction === "credit" ? 1n : -1n) * BigInt(r.amount_minor),
        0n
      )
    if (rawNet !== incoming - outgoing)
      throw Error(
        "Account perspective does not reconcile with source postings."
      )
    return {
      currency,
      incoming_minor: incoming.toString(),
      outgoing_minor: outgoing.toString(),
      internal_minor: internal.toString(),
      net_minor: (incoming - outgoing).toString(),
      internal_count: scoped.filter((m) => m.kind === "internal").length,
      movement_count: scoped.length,
    }
  })
  const groups = new Map<
    string,
    {
      id: string
      label: string
      currency: string
      credits_minor: string
      debits_minor: string
      transaction_ids: string[]
    }
  >()
  for (const m of movements.filter((m) => m.kind !== "internal")) {
    const id = JSON.stringify([m.group_id, m.currency]),
      group = groups.get(id) ?? {
        id,
        label: m.label,
        currency: m.currency,
        credits_minor: "0",
        debits_minor: "0",
        transaction_ids: [],
      }
    const field = m.kind === "incoming" ? "credits_minor" : "debits_minor"
    group[field] = (BigInt(group[field]) + BigInt(m.amount_minor)).toString()
    group.transaction_ids.push(...m.transaction_ids)
    groups.set(id, group)
  }
  return {
    totals,
    movements,
    groups: [...groups.values()].sort((a, b) => {
      if (a.currency !== b.currency) return a.currency.localeCompare(b.currency)
      const netA = BigInt(a.credits_minor) - BigInt(a.debits_minor),
        netB = BigInt(b.credits_minor) - BigInt(b.debits_minor)
      return netA === netB ? a.id.localeCompare(b.id) : netA > netB ? -1 : 1
    }),
  }
}
