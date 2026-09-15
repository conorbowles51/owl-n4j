import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, expect, it, vi } from "vitest"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import {
  FinancialAccessProvider,
  FinancialAccessNotice,
} from "./FinancialAccessProvider"
import { useFinancialAccess } from "../hooks/use-financial-access"
import { CorrectionForm } from "./CorrectionForm"
import { SavePaymentSelection } from "./SavePaymentSelection"
import { PdfReviewIntake } from "./PdfReviewIntake"
const api = vi.hoisted(() => vi.fn())
vi.mock("@/lib/api-client", () => ({ fetchAPI: api }))
const user = {
  id: "user-one",
  username: "member@example.test",
  name: "Member",
  role: "editor",
}
const response = (
  can_edit = false,
  can_upload = false,
  case_id = "case-one"
) => ({ case_id, user_id: user.id, can_edit, can_upload })
function Probe() {
  const { canEdit, canUpload, ready } = useFinancialAccess()
  return (
    <>
      <FinancialAccessNotice />
      <button disabled={!canEdit}>Edit record</button>
      <button disabled={!canUpload}>Upload file</button>
      <span>{ready ? "access-ready" : "access-unconfirmed"}</span>
    </>
  )
}
function setup() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  const view = (caseId = "case-one") => (
    <QueryClientProvider client={client}>
      <FinancialAccessProvider caseId={caseId}>
        <Probe />
      </FinancialAccessProvider>
    </QueryClientProvider>
  )
  return { client, ...render(view()), view }
}
beforeEach(() => {
  api.mockReset()
  useAuthStore.setState({ user, isAuthenticated: true })
})
it("offers no edits or uploads until exact permissions arrive, regardless of the displayed editor role", async () => {
  let resolve!: (value: unknown) => void
  api.mockImplementation(
    () =>
      new Promise((r) => {
        resolve = r
      })
  )
  setup()
  expect(screen.getByRole("button", { name: "Edit record" })).toBeDisabled()
  expect(screen.getByRole("button", { name: "Upload file" })).toBeDisabled()
  await act(async () => resolve(response()))
  expect(await screen.findByText("access-ready")).toBeInTheDocument()
  expect(screen.getByText(/This case is read-only/)).toBeInTheDocument()
  expect(screen.getByRole("button", { name: "Edit record" })).toBeDisabled()
})
it.each([
  [true, false],
  [false, true],
  [true, true],
])("keeps editing %s and uploading %s independent", async (edit, upload) => {
  api.mockResolvedValue(response(edit, upload))
  setup()
  await screen.findByText("access-ready")
  expect(screen.getByRole("button", { name: "Edit record" })).toHaveProperty(
    "disabled",
    !edit
  )
  expect(screen.getByRole("button", { name: "Upload file" })).toHaveProperty(
    "disabled",
    !upload
  )
})
it("removes old editing access after a failed recheck and supports a deliberate retry", async () => {
  api.mockResolvedValue(response(true, true))
  const { client } = setup()
  await screen.findByText("access-ready")
  api.mockRejectedValue(Error("Membership removed"))
  await act(async () => {
    await client.invalidateQueries({ queryKey: ["financial-case-access"] })
  })
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Case access could not be checked"
  )
  expect(screen.getByRole("button", { name: "Edit record" })).toBeDisabled()
  api.mockResolvedValue(response(false, false))
  fireEvent.click(screen.getByRole("button", { name: "Check access again" }))
  await screen.findByText("access-ready")
  expect(screen.getByRole("button", { name: "Edit record" })).toBeDisabled()
})
it("does not carry edit access into another case or another signed-in user", async () => {
  api.mockResolvedValue(response(true, true))
  const { rerender, view } = setup()
  await screen.findByText("access-ready")
  api.mockImplementation(() => new Promise(() => {}))
  rerender(view("case-two"))
  expect(screen.getByRole("button", { name: "Edit record" })).toBeDisabled()
  rerender(view())
  await screen.findByText("access-ready")
  act(() =>
    useAuthStore.setState({
      user: { ...user, id: "user-two", username: "two@example.test" },
    })
  )
  expect(screen.getByRole("button", { name: "Edit record" })).toBeDisabled()
})
it.each([
  response(true, true, "wrong-case"),
  { ...response(true, true), user_id: "wrong-user" },
  { ...response(), can_edit: "true" },
])("rejects a mismatched or malformed response", async (value) => {
  api.mockResolvedValue(value)
  setup()
  await screen.findByRole("alert")
  expect(screen.getByRole("button", { name: "Edit record" })).toBeDisabled()
  expect(screen.getByRole("button", { name: "Upload file" })).toBeDisabled()
})
it("does not fetch permissions without a signed-in identity", async () => {
  useAuthStore.setState({ user: null, isAuthenticated: false })
  setup()
  await waitFor(() => expect(api).not.toHaveBeenCalled())
  expect(screen.getByRole("button", { name: "Edit record" })).toBeDisabled()
})
it("mutation-only forms are absent without a permission provider", () => {
  const { container } = render(
    <>
      <CorrectionForm
        caseId="c"
        transactionId="t"
        currency="EUR"
        onClose={() => {}}
      />
      <SavePaymentSelection caseId="c" ids={["t"]} />
      <PdfReviewIntake caseId="c" onReady={() => {}} />
    </>
  )
  expect(container).toBeEmptyDOMElement()
  expect(api).not.toHaveBeenCalled()
})

it.each([401, 403, 404])(
  "removes case contents and offers a useful recovery action after HTTP %s",
  async (status) => {
    api.mockResolvedValue(response(true, true))
    const { client } = setup()
    await screen.findByText("access-ready")
    api.mockRejectedValue(Object.assign(Error("Access denied"), { status }))
    await act(async () => {
      await client.invalidateQueries({ queryKey: ["financial-case-access"] })
    })
    expect(await screen.findByRole("alert")).toHaveTextContent(
      status === 401
        ? "Your session has expired"
        : "This case is no longer available"
    )
    expect(screen.queryByRole("button", { name: "Edit record" })).toBeNull()
    expect(
      screen.getByRole("link", {
        name: status === 401 ? "Sign in again" : "Open cases",
      })
    ).toHaveAttribute("href", status === 401 ? "/login" : "/cases")
  }
)
