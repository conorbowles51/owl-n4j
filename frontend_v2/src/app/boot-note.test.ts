import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"

/** The wait has words from the first paint (lx-convspeed): the note is in the HTML itself, ahead of every script, and
 * React replaces it when the app mounts. */
describe("index.html", () => {
  const html = readFileSync(resolve(__dirname, "../../index.html"), "utf8")

  it("says the app is opening inside the root, before any script has run", () => {
    const root = html.match(/<div id="root">(.*?)<\/div>/s)?.[1] ?? ""
    expect(root).toContain('role="status"')
    expect(root).toContain("Opening Loupe")
    expect(html.indexOf("Opening Loupe")).toBeLessThan(html.indexOf('src="/src/main.tsx"'))
  })
})
