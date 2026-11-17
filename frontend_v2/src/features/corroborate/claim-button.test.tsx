import { afterEach, describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen } from "@testing-library/react"
import { setSwitch } from "@/lib/ui-switches"
import { ClaimButton } from "./ClaimButton"
import { CLAIM_EVENT, type ClaimComposerRequest } from "./claim-composer"

afterEach(() => setSwitch("corroborate-v2", false))

describe("Corroborate this claim", () => {
  it("shows nothing while the switch is off", () => {
    setSwitch("corroborate-v2", false)
    render(<ClaimButton sentence="I was home all evening on the 3rd" />)
    expect(screen.queryByText("Corroborate this claim")).toBeNull()
  })
  it("opens the claim composer with the line and where it came from, and runs nothing", () => {
    setSwitch("corroborate-v2", true)
    const heard = vi.fn((e: Event) => (e as CustomEvent<ClaimComposerRequest>).detail)
    window.addEventListener(CLAIM_EVENT, heard)
    render(<ClaimButton sentence="I was home all evening on the 3rd" source={{ type: "statement_line", id: "s1" }} />)
    fireEvent.click(screen.getByText("Corroborate this claim"))
    window.removeEventListener(CLAIM_EVENT, heard)
    expect(heard).toHaveBeenCalledTimes(1)
    expect(heard.mock.results[0].value).toEqual({ text: "I was home all evening on the 3rd", source: { type: "statement_line", id: "s1" } })
  })
})
