import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { OPEN_WORKFLOW } from "@/features/guidance/workflows/open"
import { FinancialGuide } from "./FinancialGuide"

const GUIDE = "# Loupe financial user guide\n\n## Step-by-step workflows\n\n- [Where did the money go?](#workflow=money). Use this when.\n"

describe("the Financial guide", () => {
  afterEach(() => vi.unstubAllGlobals())

  it("opens a step-by-step workflow from its link and closes itself", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(GUIDE, { status: 200 })))
    const opened = vi.fn()
    window.addEventListener(OPEN_WORKFLOW, opened)
    try {
      render(<FinancialGuide />)
      fireEvent.click(screen.getByRole("button", { name: /Financial guide/ }))
      const link = await screen.findByRole("link", { name: "Where did the money go?" })
      fireEvent.click(link)
      expect(opened).toHaveBeenCalledTimes(1)
      expect((opened.mock.calls[0][0] as CustomEvent).detail).toEqual({ id: "money" })
      await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull())
    } finally {
      window.removeEventListener(OPEN_WORKFLOW, opened)
    }
  })
})
