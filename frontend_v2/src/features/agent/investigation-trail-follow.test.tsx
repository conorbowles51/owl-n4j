import { render } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { firstShownDetails, useFollowNewestStep } from "./investigation-trail-follow"

const PHONE = "I'm reading this case's phone records in full, citing each record."

describe("firstShownDetails", () => {
  it("shows a repeated step line once", () => {
    expect(firstShownDetails([PHONE, PHONE, "Other", PHONE, null])).toEqual([PHONE, null, "Other", null, null])
  })
})

function Trail({ count, live }: { count: number; live: boolean }) {
  const newest = useFollowNewestStep(count, live)
  return (
    <div>
      {Array.from({ length: count }, (_, index) => (
        <div key={index} data-step={index} ref={index === count - 1 ? newest : undefined}>
          step {index}
        </div>
      ))}
    </div>
  )
}

describe("useFollowNewestStep", () => {
  afterEach(() => vi.restoreAllMocks())

  function rectFor(visible: (step: number) => boolean) {
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
      const step = Number(this.dataset.step ?? -1)
      const top = visible(step) ? 100 : 5000
      return { top, bottom: top + 40, left: 0, right: 100, width: 100, height: 40, x: 0, y: top, toJSON() {} } as DOMRect
    })
  }

  it("scrolls a new step into view while the reader follows the trail", () => {
    const scroll = vi.fn()
    HTMLElement.prototype.scrollIntoView = scroll
    rectFor(() => true)
    const { rerender } = render(<Trail count={3} live />)
    rerender(<Trail count={4} live />)
    expect(scroll).toHaveBeenCalledTimes(1)
  })

  it("keeps the reader's place after they scrolled away from the newest step", () => {
    const scroll = vi.fn()
    HTMLElement.prototype.scrollIntoView = scroll
    rectFor((step) => step < 1)
    const { rerender } = render(<Trail count={3} live />)
    rerender(<Trail count={4} live />)
    expect(scroll).not.toHaveBeenCalled()
  })

  it("does not move a finished trail", () => {
    const scroll = vi.fn()
    HTMLElement.prototype.scrollIntoView = scroll
    rectFor(() => true)
    const { rerender } = render(<Trail count={3} live={false} />)
    rerender(<Trail count={4} live={false} />)
    expect(scroll).not.toHaveBeenCalled()
  })
})
