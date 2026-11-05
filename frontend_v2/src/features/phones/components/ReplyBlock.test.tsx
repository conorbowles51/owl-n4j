import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { TooltipProvider } from "@/components/ui/tooltip"
import { row } from "../lib/copy-rows.test"
import type { ParticipantLabelData, ReplyLink } from "../schemas"
import { ReplyBlock } from "./ReplyBlock"

/** Replies, quotes and forwards on a row (03 section 6.6). Synthetic data only. */
const author: ParticipantLabelData = { identity_key: "phone:+12025550188", name: "Ben Okafor", name_basis: "contact_on_this_phone", is_owner: false, owner_basis: null, identifier: { kind: "phone", display: "+1 202-555-0188" }, case_names: [] }
const target = { event_uid: "e0", record_uid: "r0", thread_key: "t", thread_title: "Family", same_thread: true, kind: "message", from: author, time: "Tue, Mar 14, 2023", excerpt: "the first words", chars: 900, subject: null, flags: ["Deleted"] }
const found: ReplyLink = { kind: "reply", original_id: "AB12", state: "found", target }

const show = (over: Parameters<typeof row>[0], onGo = vi.fn()) => render(<TooltipProvider><ReplyBlock row={row(over)} onGo={onGo} /></TooltipProvider>)

describe("ReplyBlock", () => {
  it("renders nothing on a plain message", () => {
    const { container } = show({})
    expect(container).toBeEmptyDOMElement()
  })

  it("shows the original with who wrote it, its state and a jump to it", () => {
    const onGo = vi.fn()
    show({ replies: [found] }, onGo)
    expect(screen.getByText(/Replying to Ben Okafor \(\+1 202-555-0188\), Tue, Mar 14, 2023/)).toBeInTheDocument()
    expect(screen.getByText(/the first words…/)).toBeInTheDocument()
    expect(screen.getByText("[Deleted]")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Go to this message" }))
    expect(onGo).toHaveBeenCalledWith(target, expect.objectContaining({ event_uid: "e1" }))
  })

  it("names the other conversation", () => {
    show({ replies: [{ ...found, target: { ...target, same_thread: false } }] })
    expect(screen.getByText(/in Family/)).toBeInTheDocument()
  })

  it("says when the original is not in the extraction, with the report's id, and offers no jump", () => {
    show({ replies: [{ kind: "quote", original_id: "AB12", state: "not_in_extraction", target: null }] })
    expect(screen.getByText("Quoting a message that is not in this extraction. The report gives its id: AB12.")).toBeInTheDocument()
    expect(screen.queryByRole("button")).not.toBeInTheDocument()
  })

  it("says when the report gives no id", () => {
    show({ replies: [{ kind: "reply", original_id: null, state: "not_recorded", target: null }] })
    expect(screen.getByText("Marked as a reply. The report does not say to which message.")).toBeInTheDocument()
  })

  it("marks a forward and names its author apart from the sender", () => {
    show({ forward: { original_sender: author, time_created: "Mon, Mar 1, 2023" } })
    expect(screen.getByTestId("forwarded")).toHaveTextContent("Forwarded. First written by Ben Okafor (+1 202-555-0188), Mon, Mar 1, 2023.")
  })
})
