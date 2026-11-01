// J-1a (07 section 3, gate cb-capture DONE): pick, check, send, and the stages through "Checking nothing is missing".
// Red until the phone intake exists. Uses the phones-only synthetic case and the fixture builder's C1 folder,
// built into JOURNEY_FIXTURES (default /mnt/owl-data/tmp/journey-fixtures/phones-only).
import { StepFailed } from "../lib.mjs"

const FIXTURES = process.env.JOURNEY_FIXTURES ?? "/mnt/owl-data/tmp/journey-fixtures/phones-only"

export default [
  {
    id: "J-1a",
    owner: "cb-capture",
    gate: "cb-capture DONE",
    title: "Add a phone and know it arrived whole (pick, check, send)",
    async run(ctx) {
      const { page } = ctx
      await ctx.open(ctx.cases.phonesOnly, "/evidence")
      await ctx.step("button named without the vendor", async () => {
        const button = page.getByRole("button", { name: "Add phone report (folder or ZIP)" })
        await ctx.see(button)
        const vendor = await page.getByText(/cellebrite|ufed|ufdr/i).count()
        if (vendor) throw new StepFailed("vendor name", `${vendor} elements name the vendor`)
      })
      await ctx.step("pick the folder", async () => {
        // The button opens a menu of the two forms (folder, ZIP); the folder item opens the picker.
        await ctx.click(page.getByRole("button", { name: "Add phone report (folder or ZIP)" }))
        const chooser = page.waitForEvent("filechooser")
        await ctx.click(page.getByRole("menuitem", { name: "Phone report folder" }))
        await (await chooser).setFiles(`${FIXTURES}/C1`)
      })
      await ctx.step("checking files in words within 2 s", async () => {
        await ctx.see(page.getByText(/Checking files before upload: [\d,]+ of [\d,]+/), 2000)
      }, { limitMs: 2000 })
      await ctx.step("sending with time left and the resume sentence", async () => {
        await ctx.see(page.getByText(/Sending [\d.]+ of [\d.]+ [KMG]B/), 60000)
        await ctx.see(page.getByText("If this tab closes, choose the same folder again to continue."))
      })
      await ctx.step("one card lists the stages in words", async () => {
        for (const stage of ["Checking the report", "Reading records", "Checking nothing is missing"])
          await ctx.see(page.getByText(stage), 120000)
      })
      await ctx.step("the card is also in the attention feed", async () => {
        await ctx.open(ctx.cases.phonesOnly, "")
        await ctx.see(page.getByText(/Getting C\d ready/))
      })
      ctx.atMost(3)
    },
  },
]
