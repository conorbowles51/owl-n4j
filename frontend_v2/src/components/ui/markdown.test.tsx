import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { Markdown } from "./markdown"

describe("Markdown", () => {
  it("renders Markdown formatting without executing arbitrary HTML", () => {
    render(
      <Markdown content={'**Established**\n\n<script>window.__unsafe = true</script>\n\n[unsafe](javascript:alert(1))'} />,
    )

    expect(screen.getByText("Established").tagName).toBe("STRONG")
    expect(document.querySelector("script")).toBeNull()
    expect(
      screen.queryByRole("link", { name: "unsafe" })?.getAttribute("href"),
    ).not.toBe("javascript:alert(1)")
  })
})
