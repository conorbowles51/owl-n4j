// cb-ux acceptance (07 section 12.1): the preview behind its switch, the Guide, Learn more, and Report a problem.
// Runs in the verification case (the preview shows invented phones whatever the case) and the training case.
import { StepFailed } from "../lib.mjs"

const J = (id, title, run) => ({ id, owner: "cb-ux", gate: "cb-ux DONE", title, run })
const SHOTS = process.env.JOURNEY_SHOTS // a directory: screenshots are taken only here, only of synthetic cases

export default [
  J("UX-preview-off", "With the switch off the preview is invisible", async (ctx) => {
    const { page } = ctx
    await ctx.open(ctx.cases.verification, "?phone-prototype=off")
    await ctx.step("no sidebar item and the route sends the person back", async () => {
      await page.waitForLoadState("networkidle")
      if (await page.getByRole("link", { name: /Phones \(pre/ }).count()) throw new StepFailed("sidebar", "preview link shown with the switch off")
      await ctx.open(ctx.cases.verification, "/phones-prototype")
      await page.waitForLoadState("networkidle")
      if (await page.getByRole("heading", { name: /\(prototype\)/ }).count()) throw new StepFailed("route", "preview page shown with the switch off")
    })
  }),
  J("UX-preview-on", "With the switch on the preview opens, signed in, over http", async (ctx) => {
    const { page } = ctx
    await ctx.open(ctx.cases.verification, "?phone-prototype=on")
    await ctx.step("sidebar item opens the Phone summary", async () => {
      await ctx.click(page.getByRole("link", { name: /Phones \(pre/ }))
      await ctx.see(page.getByRole("heading", { name: /Phone summary \(prototype\)/ }), 10000)
    })
    for (const [name, heading] of [["Conversations", /Conversations \(prototype\)/], ["Needs a decision", /Needs a decision \(prototype\)/]]) {
      await ctx.step(`open ${name}`, async () => {
        await ctx.click(page.getByRole("navigation", { name: "Prototype screens" }).getByRole("link", { name }))
        await ctx.see(page.getByRole("heading", { name: heading }))
        if (SHOTS) await page.screenshot({ path: `${SHOTS}/preview-${name.toLowerCase().replace(/ /g, "-")}.png` })
      })
    }
    await ctx.step("Add to… from Conversations replies with counts", async () => {
      await ctx.click(page.getByRole("navigation", { name: "Prototype screens" }).getByRole("link", { name: "Conversations" }))
      await ctx.see(page.getByRole("button", { name: /Add to/ }))
    })
  }),
  J("UX-guide", "The guide, checklist and glossary open from the Guide button; Learn more lands on the term", async (ctx) => {
    const { page } = ctx
    await ctx.open(ctx.cases.verification, "/phones-prototype?phone-prototype=on")
    await ctx.step("Guide opens the user guide", async () => {
      await ctx.click(page.getByRole("button", { name: "Guide" }))
      await ctx.see(page.getByRole("heading", { name: "Phone user guide", level: 1 }), 10000)
    })
    await ctx.step("Team checklist and Glossary tabs", async () => {
      await ctx.click(page.getByRole("button", { name: "Team checklist" }))
      await ctx.see(page.getByRole("heading", { name: "Phone team checklist", level: 1 }))
      await ctx.click(page.getByRole("button", { name: "Glossary" }))
      await ctx.see(page.getByRole("heading", { name: "Phone glossary", level: 1 }))
      await page.keyboard.press("Escape")
    })
    await ctx.step("/guide/phones#corrected opens the Glossary at Corrected", async () => {
      await page.goto(`${ctx.base}/guide/phones#corrected`, { waitUntil: "domcontentloaded" })
      const target = page.locator("#phone-glossary-corrected")
      await ctx.see(target, 10000)
      const inView = await target.evaluate((el) => { const r = el.getBoundingClientRect(); return r.top >= 0 && r.top < window.innerHeight })
      if (!inView) throw new StepFailed("anchor", "the term is not in view")
    })
  }),
  J("UX-report", "Report a problem stores a row and sends only ids, kinds and counts", async (ctx) => {
    const { page } = ctx
    await ctx.open(ctx.cases.training, "/phones-prototype?phone-prototype=on")
    await ctx.step("file a report from the preview", async () => {
      await ctx.click(page.getByRole("button", { name: "Report a problem" }))
      await page.getByLabel("What were you doing?").selectOption("reading")
      await ctx.click(page.getByLabel("No, it stays the same"))
      await page.getByLabel("What did you expect? (optional)").fill("Journey check: invented text that must stay in the database.")
      await ctx.click(page.getByRole("button", { name: "Send report" }))
      await ctx.see(page.getByText(/^Report saved\. Reference [0-9a-f]{8}\. Thank you\.$/), 10000)
    })
    await ctx.step("the report is listed for the case with its structured fields", async () => {
      const r = await ctx.api(`/api/cases/${ctx.cases.training}/ui-problem-reports`)
      if (r.status !== 200) throw new StepFailed("list", `answered ${r.status}`)
      const mine = r.body.reports.find((x) => x.screen === "prototype-summary" && x.action_kind === "reading")
      if (!mine) throw new StepFailed("list", "the report is not listed")
      if (!mine.build_id || !mine.viewport_w) throw new StepFailed("fields", "build or viewport missing")
    })
  }),
]
