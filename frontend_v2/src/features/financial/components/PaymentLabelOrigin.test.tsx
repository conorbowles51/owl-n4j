import { cleanup, render, screen } from "@testing-library/react"
import { expect, it } from "vitest"
import type { LedgerTransaction } from "../api"
import { paymentFixture } from "../lib/payment-fixture.test-support"
import { PaymentLabelOrigin } from "./PaymentLabelOrigin"

const row = (explanation: string) =>
  ({
    ...paymentFixture,
    to_name: "GRUAS DEL NORTE",
    label_sources: { to_name: { source: "investigator", explanation } },
  }) as LedgerTransaction

it("marks a name a person read from the statement as theirs, in the table and in the details", () => {
  const named = row("Named by Alex Rivera from the statement on 2026-10-29.")
  const { unmount } = render(<PaymentLabelOrigin row={named} field="to_name" />)
  expect(screen.getByText("Named by Alex Rivera from the statement").getAttribute("title")).toBe(
    "Named by Alex Rivera from the statement on 2026-10-29."
  )
  unmount()
  render(<PaymentLabelOrigin row={named} field="to_name" detail />)
  expect(screen.getByText("Named by Alex Rivera from the statement on 2026-10-29.")).toBeTruthy()
})

it("shows no 'Saved by' on the list line, whoever saved it, but keeps what Claude read first", () => {
  const { container } = render(
    <>
      <PaymentLabelOrigin row={row("Saved by Alex Rivera on 2026-10-01. Invoice on file.")} field="to_name" />
      <PaymentLabelOrigin row={row("")} field="to_name" />
    </>
  )
  expect(container.textContent).toBe("")
  cleanup()
  render(<PaymentLabelOrigin row={row('Saved by Alex. Claude read: "GRUAS DEL NRTE"')} field="to_name" />)
  expect(screen.queryByText(/Saved by/)).toBeNull()
  cleanup()
  render(<PaymentLabelOrigin row={row("Saved by Alex Rivera on 2026-10-01.")} field="to_name" detail />)
  expect(screen.getByText("Saved by Alex Rivera on 2026-10-01.")).toBeTruthy()
  cleanup()
  render(<PaymentLabelOrigin row={row('Saved by Alex. Claude read: "GRUAS DEL NRTE"')} field="to_name" />)
  expect(screen.getByTestId("claude-read").textContent).toContain('Claude read: "GRUAS DEL NRTE"')
})
