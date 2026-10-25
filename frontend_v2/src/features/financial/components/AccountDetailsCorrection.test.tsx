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
