import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

const getAnswerRatings = vi.fn()
const rateAnswer = vi.fn()
vi.mock("../api", () => ({ agentAPI: { getAnswerRatings: (...a: unknown[]) => getAnswerRatings(...a), rateAnswer: (...a: unknown[]) => rateAnswer(...a) } }))

import { AnswerRating } from "./AnswerRating"

const made = (kind: string, label: string) => ({ id: "r1", message_id: "m1", kind, label, note: "", record_ref: null })

describe("AnswerRating", () => {
  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it("offers the three ratings and sends the one chosen with its note and the picked record", async () => {
    getAnswerRatings.mockResolvedValue({ ratings: [] })
    rateAnswer.mockResolvedValue({ ratings: [made("missed_something", "Missed something")] })
    render(<AnswerRating caseId="c1" messageId="m1" />)
    for (const label of ["Missed something", "Not relevant", "Too thin"]) expect(screen.getByRole("button", { name: label })).toBeTruthy()
    fireEvent.click(screen.getByRole("button", { name: "Missed something" }))
    fireEvent.change(screen.getByLabelText(/What went wrong/), { target: { value: "The lease was in the files." } })
    fireEvent.change(screen.getByLabelText(/A record that should have been found/), { target: { value: "doc://lease/2" } })
    fireEvent.click(screen.getByRole("button", { name: "Send rating" }))
    await waitFor(() => expect(rateAnswer).toHaveBeenCalledWith("c1", "m1", {
      kind: "missed_something", note: "The lease was in the files.", recordRef: "doc://lease/2", withdraw: false, source: "agent",
    }))
    await waitFor(() => expect(screen.getByRole("status").textContent).toContain("Rated: Missed something"))
  })

  it("shows a rating already given and withdraws it on a second select", async () => {
    getAnswerRatings.mockResolvedValue({ ratings: [made("too_thin", "Too thin")] })
    rateAnswer.mockResolvedValue({ ratings: [] })
    render(<AnswerRating caseId="c1" messageId="m1" />)
    await waitFor(() => expect(screen.getByRole("button", { name: "Too thin" }).getAttribute("aria-pressed")).toBe("true"))
    fireEvent.click(screen.getByRole("button", { name: "Too thin" }))
    await waitFor(() => expect(rateAnswer).toHaveBeenCalledWith("c1", "m1", expect.objectContaining({ kind: "too_thin", withdraw: true })))
    await waitFor(() => expect(screen.queryByRole("status")).toBeNull())
  })

  it("rates a chat answer through the same call with its source", async () => {
    getAnswerRatings.mockResolvedValue({ ratings: [] })
    rateAnswer.mockResolvedValue({ ratings: [made("not_relevant", "Not relevant")] })
    render(<AnswerRating caseId="c1" messageId="m1" source="chat" />)
    await waitFor(() => expect(getAnswerRatings).toHaveBeenCalledWith("m1", "chat"))
    fireEvent.click(screen.getByRole("button", { name: "Not relevant" }))
    fireEvent.click(screen.getByRole("button", { name: "Send rating" }))
    await waitFor(() =>
      expect(rateAnswer).toHaveBeenCalledWith("c1", "m1", expect.objectContaining({ kind: "not_relevant", source: "chat" })),
    )
  })

  it("says so when the rating could not be saved", async () => {
    getAnswerRatings.mockResolvedValue({ ratings: [] })
    rateAnswer.mockRejectedValue(new Error("Only an answer from the agent can be rated."))
    render(<AnswerRating caseId="c1" messageId="m1" />)
    fireEvent.click(screen.getByRole("button", { name: "Not relevant" }))
    fireEvent.click(screen.getByRole("button", { name: "Send rating" }))
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("can be rated"))
  })
})
