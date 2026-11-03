import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { ReportProblem, type ReportSender } from "./report-problem"
import { ACTIONS } from "./report-problem-api"

afterEach(cleanup)

describe("Report a problem", () => {
  it("sends only structured fields plus the optional text, and gives a reference", async () => {
    const send = vi.fn<ReportSender>(async () => ({ id: "x", reference: "ab12cd34" }))
    render(<ReportProblem defaultOpen caseId="c1" screen="conversations" scope={{ messages: 12, phones: 2 }} components={["phone-table"]} send={send} />)
    expect(screen.getByRole("button", { name: "Send report" })).toBeDisabled()
    fireEvent.change(screen.getByLabelText("What were you doing?"), { target: { value: "filtering" } })
    fireEvent.click(screen.getByLabelText("No, it stays the same"))
    fireEvent.change(screen.getByLabelText("What did you expect? (optional)"), { target: { value: "  the count to match  " } })
    fireEvent.click(screen.getByRole("button", { name: "Send report" }))
    await screen.findByText("Report saved. Reference ab12cd34. Thank you.")
    const [caseId, report] = send.mock.calls[0]
    expect(caseId).toBe("c1")
    expect(Object.keys(report).sort()).toEqual(["action_kind", "build_id", "components", "expected", "last_request_id", "refresh_changes",
      "scope", "screen", "viewport_h", "viewport_w"])
    expect(report).toMatchObject({ screen: "conversations", action_kind: "filtering", refresh_changes: "no", build_id: "dev",
      scope: { messages: 12, phones: 2 }, components: ["phone-table"], expected: "the count to match" })
  })

  it("keeps the answers and says so when the save fails", async () => {
    const send = vi.fn(async () => {
      throw new Error("You do not have access to this case")
    })
    render(<ReportProblem defaultOpen caseId="c1" screen="conversations" send={send} />)
    fireEvent.change(screen.getByLabelText("What were you doing?"), { target: { value: "other" } })
    fireEvent.click(screen.getByRole("button", { name: "Send report" }))
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("Your answers are kept; send again."))
    expect((screen.getByLabelText("What were you doing?") as HTMLSelectElement).value).toBe("other")
  })

  it("lists exactly the actions the server accepts", () => {
    expect(ACTIONS.map((a) => a.id)).toEqual(["reading", "searching", "filtering", "selecting", "adding-to", "deciding", "copying",
      "exporting", "opening-a-record", "waiting", "other"])
  })
})
