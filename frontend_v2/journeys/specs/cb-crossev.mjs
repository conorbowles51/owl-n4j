// cb-crossev DONE: J-3b (Graph start), J-5b (money lane). Uses the training case: two phones and a ledger.
const J = (id, title, run) => ({ id, owner: "cb-crossev", gate: "cb-crossev DONE", title, run })

export default [
  J("J-3b", "Everything between two people, started from a Graph edge", async (ctx) => {
    const { page } = ctx
    await ctx.open(ctx.cases.training, "/graph")
    await ctx.step("a communication edge opens Conversations scoped to the pair with the same count", async () => {
      await ctx.click(page.getByRole("button", { name: /messages between/ }).first())
      await ctx.see(page.getByText(/[\d,]+ messages( and [\d,]+ calls)? between .+ on \d+ phones?/))
    })
  }),
  J("J-5b", "Money lane: a payment on its day, never at a time", async (ctx) => {
    const { page } = ctx
    await ctx.open(ctx.cases.training, "/timeline")
    await ctx.step("a payment opens the window and says it has a date but no time", async () => {
      // select a payment's card on the Timeline (an event card, not the type filter), then open the window from the bar
      await ctx.click(page.locator("article[role=button]").filter({ hasText: "FinancialTransaction" }).first())
      await ctx.see(page.getByText(/^The day of ".+", \d{4}-\d{2}-\d{2}$/))
      await ctx.click(page.getByRole("button", { name: "Open the window around this" }).first())
      await ctx.see(page.getByRole("region", { name: /Lane: Money/ }))
      await ctx.see(page.getByText("This payment has a date but no time. Showing the whole day."))
    })
  }),
]
