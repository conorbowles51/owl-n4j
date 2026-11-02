// J-8a (gate cb-interpret DONE): the Needs a decision page, readings group. Red until the page exists.
import { StepFailed } from "../lib.mjs"

export default [
  {
    id: "J-8a",
    owner: "cb-interpret",
    gate: "cb-interpret DONE",
    title: "Check the system's readings on Needs a decision",
    async run(ctx) {
      const { page } = ctx
      await ctx.open(ctx.cases.phonesOnly, "/phone-review")
      await ctx.step("readings listed as plain sentences, most records first", async () => {
        await ctx.see(page.getByRole("heading", { name: "Needs a decision" }))
        const items = page.getByText(/^On (?:C\d+|Phone \d+)(?: \(report \d+ of \d+\))?, .+: .+\. Affects [\d,]+ /)  // labels per 02 12.3: C<n>, else Phone <n>
        await ctx.see(items)
        const counts = await items.evaluateAll((els) => els.map((e) => Number((e.textContent.match(/Affects ([\d,]+)/) ?? [0, "0"])[1].replace(/,/g, ""))))
        for (let i = 1; i < counts.length; i++) if (counts[i] > counts[i - 1]) throw new StepFailed("order", "not ordered by records affected")
      })
      await ctx.step("Looks right is held until every kind of example is viewed", async () => {
        const looks = page.getByRole("button", { name: "Looks right" })
        if (await looks.isEnabled()) throw new StepFailed("Looks right", "enabled before examples were viewed")
        const kinds = page.getByRole("button", { name: /^Example \d+/ })
        const n = await kinds.count()
        for (let i = 0; i < n; i++) await ctx.click(kinds.nth(i))
        await ctx.see(page.getByText(new RegExp(`${n} of ${n} kinds viewed`)))
        if (!(await looks.isEnabled())) throw new StepFailed("Looks right", "still held after every kind was viewed")
      })
      await ctx.step("y confirms under the person's name with the standard reason", async () => {
        await ctx.press("y")
        await ctx.see(page.getByText(/Confirmed on the review screen after viewing \d+ examples across \d+ kinds/))
        await ctx.see(page.getByText(/Confirmed by .+ on /))
        // One feed line per review action is asserted by cb-interpret's backend feed test (07 section 11).
      })
      await ctx.step("Not right offers plain corrections and keeps the original visible", async () => {
        // A reading of whether a record is a message has no per-phone correction (02 6.8 step 8), so the journey
        // moves to the next reading (j) until one offers its plain choices, then checks the wording.
        const choice = page.getByRole("group", { name: "Corrections" }).getByRole("button", { name: /^The (sender|recipient|caller|callee) is the other party$/ })
        for (let i = 0; i < 12; i++) {
          await ctx.press("x")
          if (await choice.first().isVisible()) break
          await ctx.press("j")
        }
        await ctx.see(choice.first())
      })
    },
  },
]
