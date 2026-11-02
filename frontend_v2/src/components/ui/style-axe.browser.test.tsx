import { composeStories, setProjectAnnotations } from "@storybook/react-vite"
import { cleanup, render } from "@testing-library/react"
import axe from "axe-core"
import type React from "react"
import { afterEach, describe, expect, it } from "vitest"
import * as preview from "../../../.storybook/preview"
import { resetKeymapForTest } from "@/lib/keymap"
import "@/styles/globals.css"

/**
 * Every style story (lx-style: status set, type scale) passes axe in light and dark, in a real
 * browser, with colour contrast checked. Any violation fails, whatever its impact. Same check as the phone kit's
 * kit-axe.browser.test.tsx.
 */
setProjectAnnotations([preview])

type ComposedStory = (() => React.JSX.Element) & { parameters: Record<string, unknown>; run?: () => Promise<void> }

const modules = import.meta.glob("./stories/*.stories.tsx", { eager: true }) as Record<string, Record<string, unknown>>

afterEach(() => {
  cleanup()
  resetKeymapForTest()
})

describe("style stories pass axe", () => {
  for (const [file, mod] of Object.entries(modules)) {
    const stories = composeStories(mod as Parameters<typeof composeStories>[0]) as unknown as Record<string, ComposedStory>
    for (const [name, Story] of Object.entries(stories)) {
      it(`${file.replace("./stories/", "")} ${name}`, async () => {
        const theme = (Story.parameters as { theme?: string }).theme
        expect(theme, "each style story names its theme").toMatch(/^(light|dark)$/)
        await Story.run?.()
        if (!Story.run) render(<Story />)
        await new Promise((r) => setTimeout(r, 50))
        expect(document.documentElement.classList.contains("dark")).toBe(theme === "dark")
        const result = await axe.run(document.body, {
          runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"] },
          rules: { region: { enabled: false } },
        })
        const lines = result.violations.map(
          (v) => `${v.id} (${v.impact}): ${v.nodes.length} node(s): ${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(" | ")}`
        )
        expect(lines, lines.join("\n")).toEqual([])
      })
    }
  }
})
