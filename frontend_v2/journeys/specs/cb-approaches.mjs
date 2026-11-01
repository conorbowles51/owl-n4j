// cb-approaches DONE: J-5c (incident window, statement-claim start), J-14b (exports from analyses).
const J = (id, title, run) => ({ id, owner: "cb-approaches", gate: "cb-approaches DONE", title, run })

export default [
  J("J-5c", "The incident window from a statement claim", async (ctx) => {
    const { page } = ctx
    await ctx.open(ctx.cases.training, "/phone-analyses/incident-window")
    await ctx.step("the incident window opens with one lane per phone", async () => {
      await ctx.see(page.getByRole("region", { name: /Lane: C5/ }), 5000)
      await ctx.see(page.getByRole("region", { name: /Lane: C6/ }))
    })
  }),
  J("J-14b", "Export from a statement check or an analysis result", async (ctx) => {
    const { page } = ctx
    await ctx.open(ctx.cases.training, "/phone-analyses")
    await ctx.step("export states scope and reading state", async () => {
      await ctx.click(page.getByRole("button", { name: /^Export/ }).first())
      await ctx.see(page.getByText(/rows rely on readings not yet confirmed by a person/))
    })
  }),
]
