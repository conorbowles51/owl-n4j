// cb-media DONE: machine-generated text keeps its source shown and its mark until a person confirms it.
const J = (id, title, run) => ({ id, owner: "cb-media", gate: "cb-media DONE", title, run })

export default [
  J("M-transcript", "A transcript is marked machine-generated with its source above it", async (ctx) => {
    const { page } = ctx
    await ctx.open(ctx.cases.training, "/phones")
    await ctx.step("Media screen: a voice note shows its source and the Machine-generated mark", async () => {
      await ctx.click(page.getByRole("link", { name: /^C5\b/ }))
      await ctx.click(page.getByRole("link", { name: "Media" }))
      await ctx.see(page.getByText("Machine-generated"))
      await ctx.see(page.getByRole("button", { name: /Play|Listen/ }))
    })
  }),
]
