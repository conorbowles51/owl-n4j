import { render, screen } from "@testing-library/react"
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
  const note = screen.getByText("Named by Alex Rivera from the statement")
  expect(note.getAttribute("title")).toBe("Named by Alex Rivera from the statement on 2026-10-29.")
  unmount()
  render(<PaymentLabelOrigin row={named} field="to_name" detail />)
  expect(screen.getByText("Named by Alex Rivera from the statement on 2026-10-29.")).toBeTruthy()
})

it("marks other person labels with who saved or linked them", () => {
  render(
    <>
      <PaymentLabelOrigin row={row("Saved by Alex Rivera on 2026-10-01. Invoice on file.")} field="to_name" />
      <PaymentLabelOrigin row={row("Linked by an investigator to an existing party.")} field="to_name" />
      <PaymentLabelOrigin row={row("")} field="to_name" />
    </>
  )
  expect(screen.getByText("Saved by Alex Rivera")).toBeTruthy()
  expect(screen.getByText("Linked by an investigator")).toBeTruthy()
  expect(screen.getByText("Saved by a person")).toBeTruthy()
})
