// Gate F (cb-pol DONE): J-5a, J-9, J-10b. Red until Lanes, statement checks and Together exist.
import { StepFailed } from "../lib.mjs"

const J = (id, title, run) => ({ id, owner: "cb-pol", gate: "Gate F (cb-pol DONE)", title, run })

export default [
  J("J-5a", "The window around a moment, phone lanes and case lane", async (ctx) => {
    const { page } = ctx
    await ctx.open(ctx.cases.phonesOnly, "/timeline")
    await ctx.step("open the window around a record in 5 s, one lane per phone", async () => {
      await ctx.click(page.getByRole("button", { name: "Open the window around this" }).first())
      await ctx.see(page.getByRole("region", { name: /Lane: C1/ }), 5000)
      await ctx.see(page.getByRole("region", { name: /Lane: Case events/ }))
    }, { limitMs: 5000 })
    await ctx.step("window chips name the zone; No data apart from no use seen", async () => {
      await ctx.see(page.getByRole("button", { name: "±1 h" }))
      await ctx.see(page.getByText(/Eastern time|case zone/))
      const nodata = await page.getByText("No data").count()
      const quiet = await page.getByText("Phone recording, no use seen").count()
      if (nodata + quiet === 0) throw new StepFailed("bands", "neither No data nor no-use bands drawn")
    })
  }),
  J("J-9", "Test a statement against the phones", async (ctx) => {
    const { page } = ctx
    await ctx.open(ctx.cases.training, "/phone-patterns")
    await ctx.step("evaluate claims in 2 s with fixed wording and counts", async () => {
      await ctx.click(page.getByRole("button", { name: "Check a statement" }))
      await ctx.see(page.getByRole("heading", { name: /Supports \([\d,]+\)/ }), 2000)
      await ctx.see(page.getByRole("heading", { name: /Undercuts \([\d,]+\)/ }))
      await ctx.see(page.getByText("What would contradict this?"))
    })
  }),
  J("J-10b", "Were two people together (Patterns)", async (ctx) => {
    const { page } = ctx
    await ctx.open(ctx.cases.training, "/phone-patterns")
    await ctx.step("Together shows progress within 2 s and an outcome per episode", async () => {
      await ctx.click(page.getByRole("button", { name: "Together" }))
      await ctx.see(page.getByText(/Comparing [\d,]+ pairs of points|compatible|separated|undetermined/), 2000)
      await ctx.see(page.getByText(/compatible|separated|undetermined/), 60000)
    })
  }),
]
