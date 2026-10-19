/**
 * What the dialog says about a hold, and what it refuses to do about one.
 *
 * The gate decides; this explains.  So the assertions here are about
 * explanation rather than about safety: that nothing is described as held
 * without saying what became of the rest, that no file appears in the list
 * without a label, and — the one that is nearly a safety assertion — that
 * dismissing by any route sends nothing.
 *
 * The gate is stubbed rather than rendered.  `ProcessHoldDialog` takes a
 * `ProcessGate` and never constructs one, so a stub is the whole of its input,
 * and driving the real hook here would test `use-guarded-process.test.tsx`'s
 * subject a second time while making these cases hard to reach.
 */

import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ProcessHoldDialog } from "./ProcessHoldDialog"
import { describeHold } from "../hooks/use-guarded-process"
import type { HeldFile, HeldRequest, ProcessGate } from "../hooks/use-guarded-process"
import { ROUTE_OUTCOME_DESCRIPTION, ROUTE_OUTCOME_LABEL } from "../utils/financial-route"

const toastMocks = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
  warning: vi.fn(),
  info: vi.fn(),
}))

vi.mock("sonner", () => ({ toast: toastMocks }))

// Not called by anything here, but importing the hook module for its types and
// `describeHold` pulls the API client in with it.
vi.mock("../api", () => ({ evidenceAPI: {} }))

// Stubbed, for the same reason the gate is: this file is about what the hold
// dialog decides, and the send dialog is a subject in its own right with its
// own file. Rendering the real one would also drag a query client in here for
// the sake of a few assertions about props.
//
// The stub keeps the last `onClose` it was given, because the send dialog
// closing is something this component has to survive and the stub renders
// nothing to click.
const sendDialog = vi.hoisted(() => ({ close: () => {} }))

vi.mock("@/features/financial/components/SendToLedgerDialog", () => ({
  SendToLedgerDialog: (props: {
    caseId: string
    fileId: string
    fileName: string | null
    onClose: () => void
  }) => {
    sendDialog.close = props.onClose
    return (
      <div
        data-testid="send-dialog"
        data-case={props.caseId}
        data-file={props.fileId}
        data-name={props.fileName ?? ""}
      />
    )
  },
}))

beforeEach(() => {
  toastMocks.success.mockReset()
  toastMocks.error.mockReset()
})

const CASE_ID = "case-1"

function heldFile(overrides: Partial<HeldFile> & { file_id: string }): HeldFile {
  return {
    file_name: `${overrides.file_id}.pdf`,
    claimants: [],
    detected_format: null,
    outcome: "native",
    blocks_document_processing: true,
    reason: null,
    ...overrides,
  }
}

function heldRequest(overrides: Partial<HeldRequest> = {}): HeldRequest {
  return {
    request: { fileIds: ["a"] },
    held: [heldFile({ file_id: "a" })],
    cleared: [],
    summary: null,
    checkError: null,
    ...overrides,
  }
}

/**
 * The footer button by that name, as distinct from radix's own.
 *
 * `DialogContent` renders a corner X of its own carrying a `sr-only` "Close",
 * so when the footer button is also "Close" there are two buttons with that
 * accessible name and `getByRole` refuses to choose. Found by printing the
 * DOM. The two are told apart by `data-slot`, which radix sets on its own and
 * nothing sets on ours.
 */
function footerButton(name: string | RegExp): HTMLElement {
  const matches = screen
    .getAllByRole("button", { name })
    .filter((button) => button.getAttribute("data-slot") !== "dialog-close")
  expect(matches, `expected exactly one footer button matching ${name}`).toHaveLength(1)
  return matches[0]
}

/** A gate that holds what it is given and records what is asked of it. */
function stubGate(held: HeldRequest | null, overrides: Partial<ProcessGate> = {}): ProcessGate {
  return {
    // The gate carries the case so the dialog can offer a bank file somewhere
    // to go. Spread last, so a case passed in an override still wins.
    caseId: CASE_ID,
    start: vi.fn().mockResolvedValue("held"),
    release: vi.fn().mockResolvedValue(0),
    dismiss: vi.fn(),
    held,
    isChecking: false,
    isBusy: false,
    recordAdmission: vi.fn(),
    processAdmitted: vi.fn().mockResolvedValue("started"),
    isProcessing: false,
    ...overrides,
  }
}

/** The dialog's heading, which `DialogTitle` renders as the only one present. */
function title(held: HeldRequest): string {
  render(<ProcessHoldDialog gate={stubGate(held)} />)
  return screen.getByRole("heading").textContent ?? ""
}

describe("the heading", () => {
  // Four shapes because a hold has four, and the middle two are the ones a
  // count of `held.length` alone gets wrong.
  //
  // Asserted through the render rather than by calling `holdTitle`, which is
  // not exported: a file that exports a helper beside its component trips
  // `react-refresh/only-export-components`, and the heading is what a person
  // reads anyway. A mutant that computed the right string and then failed to
  // render it would survive the direct call and fail here.
  it("counts the held files", () => {
    expect(title(heldRequest({ held: [heldFile({ file_id: "a" })] }))).toBe(
      "1 file was held back"
    )
  })

  it("pluralises", () => {
    expect(
      title(heldRequest({ held: [heldFile({ file_id: "a" }), heldFile({ file_id: "b" })] }))
    ).toBe("2 files were held back")
  })

  it("does not say zero were held when the check could not answer", () => {
    // The trap this exists for: `${held.length} files were held back` reads
    // "0 files were held back" over a dialog that opened precisely because
    // something went unanswered.
    expect(title(heldRequest({ held: [], cleared: ["a"], checkError: "timed out" }))).toBe(
      "Some files could not be checked"
    )
  })

  it("says nothing was sent when neither side has anything in it", () => {
    expect(title(heldRequest({ held: [], cleared: [], checkError: "404 Not Found" }))).toBe(
      "Nothing was sent"
    )
  })
})

describe("ProcessHoldDialog", () => {
  it("renders nothing when the gate is holding nothing", () => {
    const { container } = render(<ProcessHoldDialog gate={stubGate(null)} />)
    expect(container).toBeEmptyDOMElement()
    // The portal too: radix renders outside the container, so an empty
    // container on its own would not prove the dialog is absent.
    expect(screen.queryByRole("dialog")).toBeNull()
  })

  it("says what was held and what became of the rest", () => {
    const held = heldRequest({ cleared: ["b", "c"] })
    render(<ProcessHoldDialog gate={stubGate(held)} />)

    expect(screen.getByText("1 file was held back")).toBeInTheDocument()
    // The shared sentence rather than one of this component's own, so that the
    // seven screens cannot come to describe one event seven ways.
    expect(screen.getByText(describeHold(held))).toBeInTheDocument()
    // Asserted literally as well, so that a `describeHold` returning an empty
    // string could not satisfy the line above by matching an empty node.
    expect(
      screen.getByText(
        "1 file looks like bank records and was held back. 2 other files are ready to process."
      )
    ).toBeInTheDocument()
  })

  it("labels and names every held file", () => {
    render(
      <ProcessHoldDialog
        gate={stubGate(
          heldRequest({
            held: [
              heldFile({ file_id: "a", file_name: "march.camt", outcome: "native" }),
              heldFile({ file_id: "b", file_name: "april.dat", outcome: "ambiguous" }),
            ],
          })
        )}
      />
    )

    expect(screen.getByText("march.camt")).toBeInTheDocument()
    expect(screen.getByText("april.dat")).toBeInTheDocument()
    expect(screen.getByText(ROUTE_OUTCOME_LABEL.native)).toBeInTheDocument()
    expect(screen.getByText(ROUTE_OUTCOME_LABEL.ambiguous)).toBeInTheDocument()
  })

  it("labels a file the service blocked for a reason its outcome does not carry", () => {
    // The reason this does not reuse `RouteBadge`. The badge renders nothing
    // for `not_native`, because an ordinary document needs no label on a list
    // of a thousand files -- but such a file can still be held, via the
    // service's flag, and it would then be the one row here explaining nothing.
    render(
      <ProcessHoldDialog
        gate={stubGate(
          heldRequest({
            held: [heldFile({ file_id: "a", outcome: "not_native", reason: "Quarantined" })],
          })
        )}
      />
    )

    expect(screen.getByText(ROUTE_OUTCOME_LABEL.not_native)).toBeInTheDocument()
    expect(screen.getByText("Quarantined")).toBeInTheDocument()
  })

  it("falls back to the id when a file has no name", () => {
    // A file with no name still has to be findable on the list behind this
    // dialog, and a blank row is worse than an ugly one.
    render(
      <ProcessHoldDialog
        gate={stubGate(heldRequest({ held: [heldFile({ file_id: "f-42", file_name: null })] }))}
      />
    )

    expect(screen.getByText("f-42")).toBeInTheDocument()
  })

  it("explains each held file, with the evidence behind the label", () => {
    render(
      <ProcessHoldDialog
        gate={stubGate(
          heldRequest({
            held: [heldFile({ file_id: "a", outcome: "native", detected_format: "camt053" })],
          })
        )}
      />
    )

    expect(screen.getByText(ROUTE_OUTCOME_DESCRIPTION.native)).toBeInTheDocument()
    // "Bank file" is not something a person can act on; "camt.053" is.
    expect(screen.getByText("Format: camt.053")).toBeInTheDocument()
  })

  it("offers to send the files that were cleared", async () => {
    const gate = stubGate(heldRequest({ cleared: ["b", "c"] }), {
      release: vi.fn().mockResolvedValue(2),
    })
    render(<ProcessHoldDialog gate={gate} />)

    // Wrapped because the click is only the first half: `handleRelease` sets
    // `isReleasing` back to false after awaiting, and that second update lands
    // outside the click's own act scope.
    await act(async () => {
      fireEvent.click(footerButton(/Process 2 other files/))
    })

    expect(gate.release).toHaveBeenCalledTimes(1)
  })

  it("says how many were sent", async () => {
    const gate = stubGate(heldRequest({ cleared: ["b"] }), {
      release: vi.fn().mockResolvedValue(1),
    })
    render(<ProcessHoldDialog gate={gate} />)

    fireEvent.click(footerButton(/Process 1 other file/))

    await waitFor(() => expect(toastMocks.success).toHaveBeenCalledWith("Processing 1 file"))
  })

  it("says nothing when the release sent nothing", async () => {
    // `release` reports its own failure. A success toast on top of that would
    // be two messages about one event, and the second would be wrong.
    const gate = stubGate(heldRequest({ cleared: ["b"] }), {
      release: vi.fn().mockResolvedValue(0),
    })
    render(<ProcessHoldDialog gate={gate} />)

    fireEvent.click(footerButton(/Process 1 other file/))

    await waitFor(() => expect(gate.release).toHaveBeenCalled())
    expect(toastMocks.success).not.toHaveBeenCalled()
  })

  it("offers no send at all when the check cleared nothing", () => {
    const gate = stubGate(heldRequest({ held: [], cleared: [], checkError: "404 Not Found" }))
    render(<ProcessHoldDialog gate={gate} />)

    expect(screen.queryByRole("button", { name: /Process/ })).toBeNull()
    // And the remaining button says so: there is nothing to cancel.
    expect(footerButton("Close")).toBeInTheDocument()
  })

  it("calls the way out a cancel when there is something to cancel", () => {
    render(<ProcessHoldDialog gate={stubGate(heldRequest({ cleared: ["b"] }))} />)

    expect(footerButton("Cancel")).toBeInTheDocument()
  })

  it("dismisses without sending anything", () => {
    const gate = stubGate(heldRequest({ cleared: ["b"] }))
    render(<ProcessHoldDialog gate={gate} />)

    fireEvent.click(footerButton("Cancel"))

    expect(gate.dismiss).toHaveBeenCalledTimes(1)
    expect(gate.release).not.toHaveBeenCalled()
  })

  it("treats the corner X as a dismissal rather than a release", () => {
    // A third way out, and not one this component wrote: `DialogContent`
    // supplies it. It was found by a name collision in the test above rather
    // than by reading radix, which is reason enough to pin it down -- an exit
    // nobody knew was there is an exit nobody checked the behaviour of.
    const gate = stubGate(heldRequest({ cleared: ["b"] }))
    render(<ProcessHoldDialog gate={gate} />)

    const corner = screen
      .getAllByRole("button")
      .find((button) => button.getAttribute("data-slot") === "dialog-close")
    fireEvent.click(corner!)

    expect(gate.dismiss).toHaveBeenCalledTimes(1)
    expect(gate.release).not.toHaveBeenCalled()
  })

  it("treats escape as a dismissal rather than a release", () => {
    // Losing a modal by accident must not send anything anywhere.
    const gate = stubGate(heldRequest({ cleared: ["b"] }))
    render(<ProcessHoldDialog gate={gate} />)

    fireEvent.keyDown(document.body, { key: "Escape" })

    expect(gate.dismiss).toHaveBeenCalledTimes(1)
    expect(gate.release).not.toHaveBeenCalled()
  })

  it("shows the check's own error when there is no file list to attach it to", () => {
    render(
      <ProcessHoldDialog
        gate={stubGate(heldRequest({ held: [], cleared: [], checkError: "404 Not Found" }))}
      />
    )

    // Twice: once inside the shared sentence, once on its own. Both are wanted
    // here -- the sentence says what happened, the panel shows what the service
    // actually said -- which is why this counts rather than using `getByText`.
    expect(screen.getAllByText(/404 Not Found/)).toHaveLength(2)
  })

  it("does not repeat the error beside a list of files", () => {
    // With a list present the description above it already carries the error,
    // and a second copy would be the same sentence twice on one screen.
    render(
      <ProcessHoldDialog
        gate={stubGate(
          heldRequest({
            held: [heldFile({ file_id: "a" })],
            cleared: ["b"],
            checkError: "The check returned no answer for 1 of 3 files.",
          })
        )}
      />
    )

    expect(screen.getAllByText(/The check returned no answer for 1 of 3 files\./)).toHaveLength(1)
  })

  it("does not leave a spinner over the next hold", async () => {
    // The dialog closes by `held` becoming null, which renders nothing but
    // keeps this component's state alive. Left true, `isReleasing` would open
    // the next hold showing a spinner over a button nobody had pressed, with
    // both buttons disabled -- a dialog with no way out.
    let settle: (count: number) => void = () => {}
    const gate = stubGate(heldRequest({ cleared: ["b"] }), {
      release: vi.fn().mockReturnValue(
        new Promise<number>((resolve) => {
          settle = resolve
        })
      ),
    })
    const { rerender } = render(<ProcessHoldDialog gate={gate} />)

    fireEvent.click(footerButton(/Process 1 other file/))
    await waitFor(() =>
      expect(footerButton("Cancel")).toBeDisabled()
    )

    settle(1)
    // The gate clears the hold once the release resolves; the component stays
    // mounted, which is the whole point.
    await waitFor(() => expect(toastMocks.success).toHaveBeenCalled())
    rerender(<ProcessHoldDialog gate={stubGate(null)} />)
    rerender(<ProcessHoldDialog gate={stubGate(heldRequest({ cleared: ["c"] }))} />)

    expect(footerButton("Cancel")).toBeEnabled()
    expect(footerButton(/Process 1 other file/)).toBeEnabled()
  })
})

/**
 * The one thing a held file can now be sent to.
 *
 * The offer is narrower than the hold: `belongsToLedger` is `native` alone,
 * while four outcomes block. The cases below pin that gap in both directions,
 * because the two plausible mistakes are opposite. Offering the button on every
 * held file would put an action on rows where the reading refuses the bytes --
 * a button that can only be refused. Gating it on something narrower still, or
 * on `blocks_document_processing`, would hide it from the files it exists for.
 */
describe("sending a held file to the ledger", () => {
  it("offers the ledger the one kind of file the ledger can read", () => {
    render(<ProcessHoldDialog gate={stubGate(heldRequest())} />)

    expect(screen.getByTestId("send-to-ledger-a")).toBeInTheDocument()
  })

  it("does not offer it for a file the reading would refuse", () => {
    // `ambiguous` is held, and blocking is not the test. The reading requires
    // exactly one format to claim the bytes, so this file would be turned away
    // there. `not_native` is here too because a file can be held for reasons
    // its outcome word does not carry, and being held is still not an
    // invitation to the ledger.
    for (const outcome of ["ambiguous", "not_native", "unreadable"] as const) {
      const { unmount } = render(
        <ProcessHoldDialog
          gate={stubGate(
            heldRequest({ held: [heldFile({ file_id: "a", outcome })] })
          )}
        />
      )
      expect(
        screen.queryByTestId("send-to-ledger-a"),
        `${outcome} must not be offered the ledger`
      ).not.toBeInTheDocument()
      unmount()
    }
  })

  it("names the case and the file it was pressed on", () => {
    // The send dialog cannot ask which file it is about, so a wrong id here
    // would read a different file's rows into the ledger under this row's
    // name. The case comes from the gate rather than a prop of this component
    // for the same reason.
    render(
      <ProcessHoldDialog
        gate={stubGate(
          heldRequest({
            request: { fileIds: ["a", "b"] },
            held: [
              heldFile({ file_id: "a", file_name: "march.pdf" }),
              heldFile({ file_id: "b", file_name: "april.pdf" }),
            ],
          })
        )}
      />
    )

    fireEvent.click(screen.getByTestId("send-to-ledger-b"))

    const sent = screen.getByTestId("send-dialog")
    expect(sent).toHaveAttribute("data-case", CASE_ID)
    expect(sent).toHaveAttribute("data-file", "b")
    expect(sent).toHaveAttribute("data-name", "april.pdf")
  })

  it("passes an absent name as absent rather than inventing one", () => {
    // The row falls back to the id for its own heading, but the send dialog is
    // shown the truth: a file id printed where a file name goes would look
    // like the name of the file being written to the ledger.
    render(
      <ProcessHoldDialog
        gate={stubGate(
          heldRequest({ held: [heldFile({ file_id: "a", file_name: null })] })
        )}
      />
    )

    fireEvent.click(screen.getByTestId("send-to-ledger-a"))

    expect(screen.getByTestId("send-dialog")).toHaveAttribute("data-name", "")
  })

  it("sends nothing anywhere by being opened", () => {
    // Opening the send dialog is a question, not an answer. Releasing the
    // cleared files here would process the rest of the request on the strength
    // of someone asking about one bank file.
    const gate = stubGate(heldRequest({ cleared: ["b"] }))
    render(<ProcessHoldDialog gate={gate} />)

    fireEvent.click(screen.getByTestId("send-to-ledger-a"))

    expect(gate.release).not.toHaveBeenCalled()
    expect(gate.dismiss).not.toHaveBeenCalled()
  })

  it("leaves the hold standing behind it", () => {
    // Sending one bank file says nothing about the rest of the request, and
    // the cleared files are still undecided. Closing the hold here would
    // answer that question by default, with nothing sent.
    render(<ProcessHoldDialog gate={stubGate(heldRequest({ cleared: ["b"] }))} />)

    fireEvent.click(screen.getByTestId("send-to-ledger-a"))

    expect(screen.getByRole("heading")).toHaveTextContent("1 file was held back")
    expect(footerButton(/Process 1 other file/)).toBeInTheDocument()
  })

  it("keeps one open at a time", () => {
    // The send dialog asks for a period. Two of them open at once would invite
    // the reader to answer that twice with no sign the answers differed, and
    // the second answer would be about a file they had stopped looking at.
    render(
      <ProcessHoldDialog
        gate={stubGate(
          heldRequest({
            request: { fileIds: ["a", "b"] },
            held: [heldFile({ file_id: "a" }), heldFile({ file_id: "b" })],
          })
        )}
      />
    )

    fireEvent.click(screen.getByTestId("send-to-ledger-a"))
    fireEvent.click(screen.getByTestId("send-to-ledger-b"))

    const open = screen.getAllByTestId("send-dialog")
    expect(open).toHaveLength(1)
    expect(open[0]).toHaveAttribute("data-file", "b")
  })

  it("is not open until it is asked for", () => {
    render(<ProcessHoldDialog gate={stubGate(heldRequest())} />)

    expect(screen.queryByTestId("send-dialog")).not.toBeInTheDocument()
  })

  it("closes on its own without taking the hold with it", () => {
    // `onClose` clears the row being sent. If it also dismissed the gate, a
    // reader who opened the send dialog and changed their mind would lose the
    // hold and the cleared files with it.
    const gate = stubGate(heldRequest({ cleared: ["b"] }))
    render(<ProcessHoldDialog gate={gate} />)

    fireEvent.click(screen.getByTestId("send-to-ledger-a"))
    act(() => {
      // The stub renders nothing that can be clicked, so the close is invoked
      // the way the real dialog invokes it: by calling the prop.
      sendDialog.close()
    })

    expect(screen.queryByTestId("send-dialog")).not.toBeInTheDocument()
    expect(screen.getByRole("heading")).toHaveTextContent("1 file was held back")
    expect(gate.dismiss).not.toHaveBeenCalled()
  })
})


describe("recording an admission in the hold dialog", () => {
  it("requires a reason and records it without starting processing", async () => {
    const gate = stubGate(heldRequest())
    render(<ProcessHoldDialog gate={gate} />)
    const button = screen.getByRole("button", { name: "Record decision" })
    expect(button).toBeDisabled()
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "  Checked the source  " } })
    await act(async () => { fireEvent.click(button) })
    expect(gate.recordAdmission).toHaveBeenCalledWith("a", "  Checked the source  ")
    expect(gate.processAdmitted).not.toHaveBeenCalled()
  })

  it("shows the recorded reason and makes processing a separate action", async () => {
    const gate = stubGate(heldRequest({ admissions: { a: {
      canProcess: true, decisionRecorded: true, message: "Decision recorded. Nothing sent.",
      reason: "Checked the source", reasonLabel: "Your recorded reason", routeOutcome: "ambiguous", detectedFormat: null, claimants: ["bai2", "mt940"],
    } } }))
    render(<ProcessHoldDialog gate={gate} />)
    expect(screen.getByText("Your recorded reason: Checked the source")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Record decision" })).toBeNull()
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Process this file" })) })
    expect(gate.processAdmitted).toHaveBeenCalledWith("a")
    expect(gate.recordAdmission).not.toHaveBeenCalled()
  })

  it("explains the native-file limitation before a decision is recorded", () => {
    render(<ProcessHoldDialog gate={stubGate(heldRequest())} />)
    expect(screen.getByText(/processing service still refuses/)).toBeInTheDocument()
  })

  it("displays an uncertain decision and disables actions while a request is pending", () => {
    render(<ProcessHoldDialog gate={stubGate(heldRequest({ admissionErrors: { a: "Could not confirm. Check decision history." } }), { isBusy: true })} />)
    expect(screen.getByRole("alert")).toHaveTextContent("Could not confirm")
    expect(screen.getByRole("textbox")).toBeDisabled()
    expect(screen.getByRole("button", { name: "Record decision" })).toBeDisabled()
    expect(screen.getByTestId("send-to-ledger-a")).toBeDisabled()
  })

  it("reports a processing request without offering to send the same file again", () => {
    render(<ProcessHoldDialog gate={stubGate(heldRequest({ sent: ["a"] }))} />)
    expect(screen.getByRole("status")).toHaveTextContent("Processing requested for this file")
    expect(screen.queryByRole("button", { name: "Process this file" })).toBeNull()
    expect(screen.queryByRole("button", { name: "Record decision" })).toBeNull()
  })
})
