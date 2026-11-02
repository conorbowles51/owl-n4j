import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { beforeEach, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { AccountDetailsCorrection } from "./AccountDetailsCorrection"

vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
vi.mock("../hooks/use-financial-access", () => ({
  useFinancialAccess: () => ({ canEdit: true }),
}))

const statement = (id: string, holder: string) => ({
  source_document_id: id,
  evidence_file_id: "f",
  period_id: "p",
  period_start: "2026-04-01",
  period_end: "2026-04-30",
  currency: "MXN",
  holder,
  institution: "Kapital",
  editable: true,
})
const state = (overrides = {}) => ({
  case_id: "case",
  account_id: "acct",
  holder: "LOMAS DE CHAPULTEPEC III SECCION",
  institution: "Kapital",
  account_number: "1281",
  currency: "MXN",
  statements: [statement("s1", "LOMAS DE CHAPULTEPEC III SECCION")],
  history: [],
  revision: "a".repeat(64),
  ...overrides,
})
const mount = () =>
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <AccountDetailsCorrection caseId="case" accountId="acct" />
    </QueryClientProvider>
  )
beforeEach(() => {
  vi.mocked(fetchAPI).mockReset()
})

it("previews the re-joined statement, saves with the reason, and undoes", async () => {
  const corrected = {
    id: "c1",
    kind: "correction",
    at: "2026-10-25T22:00:00Z",
    reason: "Page 1 prints the holder",
    actor_name: "Neil",
    before: {
      holder: "LOMAS DE CHAPULTEPEC III SECCION",
      institution: "Kapital",
    },
    after: {
      holder: "INGENIERIA APLICADA R2 SA DE CV",
      institution: "Kapital",
    },
  }
  let current: unknown = state()
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (url.includes("/details/preview"))
      return {
        case_id: "case",
        account_id: "acct",
        before: corrected.before,
        after: corrected.after,
        statements: [statement("s1", "LOMAS DE CHAPULTEPEC III SECCION")],
        rejoin: [
          {
            account_id: "split",
            statements: [statement("s2", "INGENIERIA APLICADA R2 SA DE CV")],
          },
        ],
        revision: "b".repeat(64),
      } as never
    if (url.includes("/details/undo")) current = state()
    else if (options?.method === "POST")
      current = state({
        holder: corrected.after.holder,
        statements: [
          statement("s1", corrected.after.holder),
          statement("s2", corrected.after.holder),
        ],
        history: [corrected],
      })
    return current as never
  })
  mount()
  const review = await screen.findByRole("button", {
    name: "Review account correction",
  })
  expect(review).toBeDisabled()
  fireEvent.change(screen.getByLabelText("Holder as printed"), {
    target: { value: "INGENIERIA APLICADA R2 SA DE CV" },
  })
  expect(review).toBeDisabled()
  fireEvent.change(screen.getByLabelText("Reason (where it is printed)"), {
    target: { value: "Page 1 prints the holder" },
  })
  fireEvent.click(review)
  expect(
    await screen.findByText(/comes back to this account/)
  ).toBeInTheDocument()
  fireEvent.click(screen.getByRole("button", { name: "Correct the account" }))
  expect(
    await screen.findByText(/Account corrected for 2 statements/)
  ).toBeInTheDocument()
  const saved = vi
    .mocked(fetchAPI)
    .mock.calls.find(
      ([url, options]) => options?.method === "POST" && !url.includes("preview")
    )!
  expect(saved[1]!.body).toMatchObject({
    expected_revision: "b".repeat(64),
    holder: "INGENIERIA APLICADA R2 SA DE CV",
    institution: null,
    reason: "Page 1 prints the holder",
  })
  const undo = await screen.findByRole("button", {
    name: /Undo this correction/,
  })
  expect(undo).toBeDisabled()
  fireEvent.change(screen.getByLabelText("Reason (where it is printed)"), {
    target: { value: "Wrong account" },
  })
  fireEvent.click(undo)
  await waitFor(() =>
    expect(vi.mocked(fetchAPI)).toHaveBeenCalledWith(
      expect.stringContaining("/accounts/acct/details/undo"),
      expect.objectContaining({
        body: expect.objectContaining({
          correction_id: "c1",
          reason: "Wrong account",
        }),
      })
    )
  )
  expect(await screen.findByText(/Correction undone/)).toBeInTheDocument()
})

it("shows a correction Claude made as Claude's until a person confirms it with what they checked", async () => {
  const byClaude = {
    id: "c2",
    kind: "correction",
    at: "2026-10-25T23:09:00Z",
    reason: "Page 1 prints the holder",
    actor_name: "Claude (for Neil Byrne)",
    origin: { kind: "model", model: "Claude", for: { name: "Neil Byrne" } },
    before: { holder: "LOMAS DE CHAPULTEPEC III SECCION", institution: "Kapital" },
    after: { holder: "INGENIERIA APLICADA R2", institution: "Kapital" },
  }
  let current: unknown = state({ holder: "INGENIERIA APLICADA R2", history: [byClaude] })
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (url.includes("/details/confirm")) {
      expect((options as { body: { basis: string; correction_id: string } }).body).toMatchObject({
        correction_id: "c2",
        basis: "Checked page 1",
      })
      current = state({
        holder: "INGENIERIA APLICADA R2",
        history: [{ ...byClaude, confirmed: { by: "Alex", at: "2026-10-29T10:00:00Z", basis: "Checked page 1" } }],
      })
    }
    return current
  })
  mount()
  expect(await screen.findByText(/Last corrected by Claude for Neil Byrne/)).toBeTruthy()
  expect(screen.getByText(/Corrected by Claude · not confirmed/)).toBeTruthy()
  const button = screen.getByRole("button", { name: /Confirm this correction/ })
  expect((button as HTMLButtonElement).disabled).toBe(true)
  // The basis goes in this correction's own box, not the shared reason box above.
  fireEvent.change(screen.getByLabelText("Reason (where it is printed)"), { target: { value: "Not the basis" } })
  expect((button as HTMLButtonElement).disabled).toBe(true)
  fireEvent.change(
    screen.getByLabelText(
      "What you checked for this correction (holder LOMAS DE CHAPULTEPEC III SECCION → INGENIERIA APLICADA R2)"
    ),
    { target: { value: "Checked page 1" } }
  )
  fireEvent.click(button)
  expect(await screen.findByText(/Confirmed by Alex on 2026-10-29: Checked page 1/)).toBeTruthy()
  await waitFor(() => expect(screen.queryByText(/not confirmed/)).toBeNull())
})

it("corrects the account number to the printed one and shows the CLABE kept with it", async () => {
  let current: unknown = state({ account_number: "128180000000238632" })
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (url.includes("/details/preview"))
      return {
        case_id: "case",
        account_id: "acct",
        before: {
          holder: "ING R2",
          institution: "Kapital",
          account_number: "128180000000238632",
        },
        after: {
          holder: "ING R2",
          institution: "Kapital",
          account_number: "194-98075-001-8",
        },
        statements: [statement("s1", "ING R2")],
        rejoin: [],
        revision: "b".repeat(64),
      } as never
    if (options?.method === "POST")
      current = state({
        account_number: "194-98075-001-8",
        account_clabe: "128180000000238632",
      })
    return current as never
  })
  mount()
  const review = await screen.findByRole("button", {
    name: "Review account correction",
  })
  fireEvent.change(screen.getByLabelText(/Account number as printed/), {
    target: { value: "194-98075-001-8" },
  })
  fireEvent.change(screen.getByLabelText("Reason (where it is printed)"), {
    target: { value: "Page 1 prints 194-98075-001-8" },
  })
  fireEvent.click(review)
  expect(
    await screen.findByText(/account 128180000000238632 → 194-98075-001-8/)
  ).toBeInTheDocument()
  fireEvent.click(screen.getByRole("button", { name: "Correct the account" }))
  expect(
    await screen.findByText(/CLABE 128180000000238632/)
  ).toBeInTheDocument()
  const saved = vi
    .mocked(fetchAPI)
    .mock.calls.find(
      ([url, options]) => options?.method === "POST" && !url.includes("preview")
    )!
  expect(saved[1]!.body).toMatchObject({
    holder: null,
    institution: null,
    account_number: "194-98075-001-8",
  })
})

it("shows a relayed confirmation as the person's, entered by someone else, beside every correction Claude made", async () => {
  const origin = { kind: "model", model: "Claude", for: { name: "Neil Byrne" } }
  const holder = {
    id: "h1",
    kind: "correction",
    at: "2026-10-25T23:09:00Z",
    reason: "Page 1 prints the holder",
    actor_name: "Claude (for Neil Byrne)",
    origin,
    before: { holder: "LOMAS DE CHAPULTEPEC III SECCION", institution: "Kapital" },
    after: { holder: "INGENIERIA APLICADA R2", institution: "Kapital" },
    confirmed: {
      by: "Neil Byrne",
      at: "2026-10-29T23:31:41Z",
      basis: "Approved by message; page 1 prints the holder.",
      // The shape an earlier relay stored: who entered it, the message, when it was given.
      relayed: { by: "Claude (fin-provenance job)", via: "coordinator message m1", at_given: "2026-10-29T05:45:00Z" },
      later_relays: [
        { by: "Claude", note: "Entered by Claude on Neil Byrne's instruction of 2026-10-30", at: "2026-10-30T17:00:00Z", basis: "Page 1 checked again." },
      ],
    },
  }
  const number = {
    id: "n1",
    kind: "correction",
    at: "2026-10-30T02:47:00Z",
    reason: "Page 1 prints the number",
    actor_name: "Claude (for Neil Byrne)",
    origin,
    before: { holder: "INGENIERIA APLICADA R2", institution: "Kapital", account_number: "1281" },
    after: { holder: "INGENIERIA APLICADA R2", institution: "Kapital", account_number: "194-98075-001-8" },
  }
  vi.mocked(fetchAPI).mockResolvedValue(state({ holder: "INGENIERIA APLICADA R2", history: [holder, number] }))
  mount()
  expect(
    await screen.findByText(
      "Confirmed by Neil Byrne · entered by Claude (fin-provenance job) (no relay note recorded), 29 Oct 2026: Approved by message; page 1 prints the holder."
    )
  ).toBeTruthy()
  expect(screen.getByText(/How this confirmation was entered \(Neil Byrne did not press Confirm in Loupe\)/)).toBeTruthy()
  expect(screen.getByText(/Entered by Claude \(fin-provenance job\) on 29 Oct 2026\. Instruction came by coordinator message m1, given 29 Oct 2026/)).toBeTruthy()
  expect(screen.getByText(/Entered by Claude on 30 Oct 2026: Entered by Claude on Neil Byrne's instruction of 2026-10-30\. Page 1 checked again\./)).toBeTruthy()
  // The later number correction is listed with its own status, and only it can still be confirmed.
  const items = Array.from(screen.getByRole("list", { name: "Corrections Claude made" }).children)
  expect(items.map((item) => item.textContent?.split(".")[0])).toEqual([
    "Claude for Neil Byrne on 25 Oct 2026: holder LOMAS DE CHAPULTEPEC III SECCION → INGENIERIA APLICADA R2",
    "Claude for Neil Byrne on 30 Oct 2026: account 1281 → 194-98075-001-8",
  ])
  expect(screen.getAllByText(/Corrected by Claude · not confirmed/)).toHaveLength(1)
  expect(screen.getAllByRole("button", { name: /Confirm this correction/ })).toHaveLength(1)
})

it("names only what a correction changed, and never doubles a note's full stop", async () => {
  // Live 1 Nov (fdaf956c 3726c790): a number-only correction read "Arrendo Serv SA de CV → Arrendo Serv SA de CV,
  // account …", and a relay note ending in a full stop was followed by another.
  const number = {
    id: "n2",
    kind: "correction",
    at: "2026-11-01T15:35:00Z",
    reason: "Page 1 prints the number",
    actor_name: "Claude (for Neil Byrne)",
    origin: { kind: "model", model: "Claude", for: { name: "Neil Byrne" } },
    before: { holder: "Arrendo Serv SA de CV", institution: "BBVA", account_number: "011280038" },
    after: { holder: "Arrendo Serv SA de CV", institution: "BBVA", account_number: "0110280038" },
    confirmed: {
      by: "Neil Byrne",
      at: "2026-11-01T15:35:28Z",
      basis: "Page 1 prints No. de Cuenta 0110280038.",
      relayed: { by: "Claude", at: "2026-11-01T15:35:28Z", via: "m1", note: "Entered by Claude on his instruction." },
    },
  }
  vi.mocked(fetchAPI).mockResolvedValue(state({ holder: "Arrendo Serv SA de CV", history: [number] }))
  mount()
  const line = await screen.findByText((_, node) => node?.tagName === "P" && /^Last corrected by/.test(node.textContent ?? ""))
  expect(line.textContent).toBe(
    "Last corrected by Claude for Neil Byrne: account 011280038 → 0110280038. Reason: Page 1 prints the number"
  )
  expect(screen.getByText("Entered by Claude on 1 Nov 2026: Entered by Claude on his instruction. Instruction came by m1")).toBeTruthy()
  expect(document.body.textContent).not.toContain("..")
})

it("shows corrections recorded on the other records of a merged account, Claude's marked until confirmed", async () => {
  // followups 2026-11-01 (fdaf956c): the panel opened on the other record of a merged account showed no
  // correction although one of its records had been corrected.
  const correction = (id: string, extra = {}) => ({
    id,
    kind: "correction",
    at: "2026-11-01T15:35:27Z",
    reason: "Page 1 prints No. de Cuenta 0110280038",
    actor_name: "Claude (for Neil Byrne)",
    origin: { kind: "model", model: "Claude", for: { name: "Neil Byrne" } },
    before: { holder: "Arrendo Serv SA de CV", institution: "BBVA", account_number: "011280038" },
    after: { holder: "Arrendo Serv SA de CV", institution: "BBVA", account_number: "0110280038" },
    ...extra,
  })
  vi.mocked(fetchAPI).mockResolvedValue(
    state({
      merged_history: [
        {
          account_id: "other",
          holder: "Arrendo Serv SA de CV",
          institution: "BBVA",
          account_number: "0110280038",
          statement_count: 1,
          revision: "b".repeat(64),
          history: [
            correction("c1", { confirmed: { by: "Neil Byrne", at: "2026-11-01T15:35:28Z", basis: "Checked page 1" } }),
          ],
        },
        {
          account_id: "empty",
          holder: "X SA",
          institution: "BBVA",
          account_number: "9",
          statement_count: 0,
          revision: "c".repeat(64),
          history: [correction("c2")],
        },
      ],
    })
  )
  mount()
  const list = await screen.findByRole("list", { name: "Corrections on other records of this merged account" })
  const items = Array.from(list.querySelectorAll("li")).map((item) => item.textContent)
  expect(items[0]).toContain("Arrendo Serv SA de CV · BBVA · 0110280038 · 1 statement")
  expect(items[0]).toContain("Corrected by Claude for Neil Byrne on 1 Nov 2026: account 011280038 → 0110280038.")
  expect(items[0]).toContain("Confirmed by Neil Byrne on 2026-11-01: Checked page 1")
  expect(items[1]).toContain("0 statements")
  expect(items[1]).toContain("Corrected by Claude · not confirmed.")
  // This record's own correction line and undo are not offered for another record's correction.
  expect(screen.queryByText(/Last corrected/)).toBeNull()
  expect(screen.queryByRole("button", { name: /Undo this correction/ })).toBeNull()
  // The unconfirmed one (on a record with no statement, so no panel of its own) is confirmed here, on its record.
  const [button] = screen.getAllByRole("button", { name: /Confirm this correction/ })
  expect((button as HTMLButtonElement).disabled).toBe(true)
  fireEvent.change(screen.getByLabelText("What you checked for this correction (account 011280038 → 0110280038)"), {
    target: { value: "Checked page 1" },
  })
  fireEvent.click(button)
  await waitFor(() =>
    expect(fetchAPI).toHaveBeenCalledWith(
      "/api/financial/statement-import/accounts/empty/details/confirm?case_id=case",
      { method: "POST", body: { expected_revision: "c".repeat(64), correction_id: "c2", basis: "Checked page 1" } }
    )
  )
  expect(await screen.findByText(/Correction confirmed as yours/)).toBeTruthy()
})

it("says so when the other records of a merged account could not be read", async () => {
  vi.mocked(fetchAPI).mockResolvedValue(state({ merged_history: null }))
  mount()
  expect(await screen.findByText(/other records of this merged account could not be loaded/)).toBeTruthy()
})
