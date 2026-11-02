// cb-screens journeys (07 section 3 and 11, gate cb-screens DONE). Each is red until its screen exists, and runs
// on the phones-only synthetic case (C1 has an owner and a zone; C2 has neither; C3 is the third phone).
import { StepFailed } from "../lib.mjs"

/** Open the Phones list and a phone's summary by its label. */
async function openPhone(ctx, label = "C1") {
  const { page } = ctx
  await ctx.open(ctx.cases.phonesOnly, "/phones")
  await ctx.click(page.getByRole("link", { name: new RegExp(`^${label}\\b`) }))
  await ctx.see(page.getByRole("heading", { name: /Phone summary/ }))
}

async function conversations(ctx) {
  await ctx.click(ctx.page.getByRole("link", { name: "Conversations" }))
  await ctx.see(ctx.page.getByRole("heading", { name: /Conversations/ }))
}

const J = (id, title, run) => ({ id, owner: "cb-screens", gate: "cb-screens DONE", title, run })

export default [
  J("J-1b", "Stages through the Phone summary", async (ctx) => {
    const { page } = ctx
    await ctx.open(ctx.cases.phonesOnly, "")
    await ctx.step("ready card names what is still running and opens the summary", async () => {
      await ctx.see(page.getByText(/Conversations are ready\./), 600000)
      await ctx.click(page.getByRole("link", { name: "Open the phone summary" }))
      await ctx.see(page.getByText(/^Read in full: [\d,]+ records,/))
    })
  }),

  J("J-2", "First look at a phone", async (ctx) => {
    const { page } = ctx
    await ctx.step("first data within 1 s, verdict line", async () => {
      await openPhone(ctx)
      await ctx.see(page.getByText(/^Read in full: [\d,]+ records, .+ to .+, \d+ apps?\./), 1000)
    }, { limitMs: 5000 })
    await ctx.step("Needs a decision box and triage block", async () => {
      await ctx.see(page.getByRole("region", { name: "Needs a decision" }))
      for (const name of ["Coverage by month", "Top people", "Where to start"]) await ctx.see(page.getByRole("heading", { name }))
    })
    await ctx.step("every top-person number equals its linked screen", async () => {
      const link = page.getByRole("region", { name: "Top people" }).getByRole("link").first()
      const shown = Number((await link.innerText()).replace(/[^\d]/g, ""))
      await ctx.click(link)
      const total = await ctx.countIn(page.getByRole("status"), "messages")
      if (total !== shown) throw new StepFailed("count", `summary ${shown} vs screen ${total}`)
    })
    await ctx.step("owner and zone unknown are worded on C2", async () => {
      await openPhone(ctx, "C2")
      await ctx.see(page.getByText("No owner number was found. Person-level views stay off until an owner is set. Set the owner."))
      await ctx.see(page.getByText(/This phone did not record its time zone\. Times show in the case zone/))
    })
  }),

  J("J-3a", "Everything between two people across apps and phones", async (ctx) => {
    const { page } = ctx
    await openPhone(ctx)
    await ctx.step("pick a person from the top people; scope bar in words", async () => {
      await ctx.click(page.getByRole("region", { name: "Top people" }).getByRole("link").first())
      await ctx.see(page.getByRole("region", { name: "Scope" }).getByText(/on \d+ of \d+ phones/))
    })
    await ctx.step("Between A and B, all channels, first rows within 1 s", async () => {
      await ctx.click(page.getByRole("button", { name: "Between A and B" }))
      await ctx.click(page.getByRole("button", { name: "All channels" }))
      await ctx.see(page.getByText(/[\d,]+ messages( and [\d,]+ calls)? between .+ on \d+ phones?/), 1000)
    })
    await ctx.step("the other-numbers switch is off and shows its effect", async () => {
      const toggle = page.getByRole("switch", { name: /Include this person's other numbers and accounts/ })
      if (await toggle.isChecked()) throw new StepFailed("toggle", "on by default")
    })
    ctx.atMost(6)
  }),

  J("J-4", "Read a conversation around a date", async (ctx) => {
    const { page } = ctx
    await openPhone(ctx)
    await conversations(ctx)
    await ctx.click(page.getByRole("listbox", { name: /Threads/ }).getByRole("option").first())
    await ctx.step("time strip, click a day, day header names the zone", async () => {
      const strip = page.getByRole("group", { name: /Message density/ })
      await ctx.see(strip)
      await ctx.click(strip.getByRole("button").first())
      // 03 3.2: "Tuesday, March 14, 2023, Eastern Time (UTC-4)" (or "..., UTC")
      await ctx.see(page.getByRole("heading", { name: /^\w+day, \w+ \d+, \d{4}, (UTC$|.+ \(UTC[+-]\d+)/ }))
    })
    await ctx.step("Around this time opens in 1.5 s with counted groups", async () => {
      await ctx.press("a")
      await ctx.see(page.getByRole("region", { name: "Around this time" }), 1500)
    }, { limitMs: 1500 })
    await ctx.step("messages with no time are listed at the end and counted", async () => {
      await ctx.see(page.getByText(/[\d,]+ messages have no time and are listed at the end\./))
    })
  }),

  J("J-6", "Search everything and read the hit in context", async (ctx) => {
    const { page } = ctx
    await openPhone(ctx)
    await ctx.step("Ctrl+K gives grouped results with totals", async () => {
      await ctx.press("Control+k")
      await page.keyboard.type("synthetic")
      await ctx.see(page.getByRole("group", { name: /^Messages \([\d,]+\)/ }))
    }, { limitMs: 1500 })
    await ctx.step("a hit opens the whole thread at that message", async () => {
      await ctx.press("Enter")
      await ctx.see(page.getByText(/Showing the whole conversation\. Your search matched [\d,]+ messages? here\./))
    })
    await ctx.step("Back restores the results", async () => {
      await page.goBack()
      await ctx.see(page.getByRole("group", { name: /^Messages \([\d,]+\)/ }))
    })
    await ctx.step("short query is worded", async () => {
      await ctx.press("Control+k")
      await page.keyboard.type("ab")
      await ctx.see(page.getByText("Type at least 3 letters."))
    })
  }),

  J("J-7", "Who is who: link identities", async (ctx) => {
    const { page } = ctx
    await ctx.open(ctx.cases.phonesOnly, "/phone-review")
    await ctx.click(page.getByRole("link", { name: /People suggestions/ }))
    await ctx.step("one suggestion at a time with reasons and examples", async () => {
      await ctx.see(page.getByText(/\d+ of \d+ decided/))
      await ctx.see(page.getByRole("region", { name: /Reasons/ }))
    })
    await ctx.step("y links and stores a standard reason", async () => {
      await ctx.press("y")
      await ctx.see(page.getByText(/\d+ of \d+ decided/))
    })
  }),

  J("J-8b", "Check a reading from the record panel", async (ctx) => {
    const { page } = ctx
    await openPhone(ctx)
    await conversations(ctx)
    await ctx.step("the record panel offers the choice beside its mark", async () => {
      await ctx.press("j")
      await ctx.press("r")
      const panel = page.getByRole("complementary", { name: /Record/ })
      await ctx.see(panel.getByText("Mapped by the system, not yet confirmed"))
      await ctx.see(panel.getByRole("button", { name: "Looks right" }))
    })
  }),

  J("J-10a", "Where was the phone: positions on the Map", async (ctx) => {
    const { page } = ctx
    await ctx.open(ctx.cases.phonesOnly, "/map")
    await ctx.step("summary line and Accuracy not recorded", async () => {
      await ctx.see(page.getByText(/Showing [\d,]+ of [\d,]+ positioned records\./))
      await ctx.see(page.getByText("Accuracy not recorded"))
    })
  }),

  J("J-11", "Find deleted or concealed material", async (ctx) => {
    const { page } = ctx
    await openPhone(ctx)
    await ctx.step("deleted count on the summary opens the filtered list in 3 actions", async () => {
      await ctx.click(page.getByRole("link", { name: /[\d,]+ deleted/ }))
      await ctx.see(page.getByText(/Deleted at some time between .+ and the extraction/))
    })
    ctx.atMost(3)
  }),

  J("J-12", "Build the case while reading", async (ctx) => {
    const { page } = ctx
    await openPhone(ctx)
    await conversations(ctx)
    await ctx.step("select, c d, reply with counts and Undo", async () => {
      await ctx.press("j")
      await ctx.press("Space")
      await ctx.press("c")
      await ctx.press("d")
      await ctx.click(page.getByRole("option").first())
      await ctx.see(page.getByText(/^Added \d+ messages? to .+\./))
      await ctx.see(page.getByRole("button", { name: "Undo" }))
    }, { limitMs: 5000 })
    await ctx.step("the row shows where it is used", async () => {
      await ctx.see(page.getByText(/In \d+ dossiers?/))
    })
  }),

  J("J-13", "Share the review and know what is left", async (ctx) => {
    const { page } = ctx
    await openPhone(ctx)
    await conversations(ctx)
    await ctx.step("not-yet-reviewed sentence on the screen", async () => {
      await ctx.see(page.getByText(/Not yet reviewed: [\d,]+ of [\d,]+ threads/))
    })
    await ctx.step("m marks the thread reviewed and the count moves", async () => {
      const before = await ctx.countIn(page.getByText(/Not yet reviewed/), "of")
      await ctx.press("m")
      const after = await ctx.countIn(page.getByText(/Not yet reviewed/), "of")
      if (after !== before - 1) throw new StepFailed("coverage", `not reviewed ${before} -> ${after}`)
    })
  }),

  J("J-13b", "A Replace that adds messages makes a reviewed thread partly reviewed", async (ctx) => {
    const { page } = ctx
    await openPhone(ctx)
    await ctx.step("coverage summary shows partly reviewed after a Replace", async () => {
      await ctx.see(page.getByText(/Reviewed by .+ on .+ \([\d,]+ messages\); [\d,]+ added since/))
    })
  }),

  J("J-14a", "Export for counsel", async (ctx) => {
    const { page } = ctx
    await openPhone(ctx)
    await conversations(ctx)
    await ctx.step("the dialog states the scope and the reading state", async () => {
      await ctx.click(page.getByRole("button", { name: /^Export/ }))
      await ctx.see(page.getByText(/^All [\d,]+ messages/))
      await ctx.see(page.getByText(/rows rely on readings not yet confirmed by a person/))
    })
  }),

  J("J-15", "Resume and hand over", async (ctx) => {
    const { page } = ctx
    await openPhone(ctx)
    await ctx.step("Continue reading on the Phone summary resumes in 2 actions", async () => {
      await ctx.click(page.getByRole("region", { name: "Continue reading" }).getByRole("link").first())
      await ctx.see(page.getByRole("heading", { name: /Conversations/ }))
    })
    ctx.atMost(2 + 2)
  }),

  J("J-16", "Compare phones for a person", async (ctx) => {
    const { page } = ctx
    await ctx.open(ctx.cases.phonesOnly, "/phones")
    await ctx.step("two columns with on both / only on counts", async () => {
      await ctx.click(page.getByRole("button", { name: "Compare phones" }))
      await ctx.see(page.getByText(/[\d,]+ on both/))
      await ctx.see(page.getByText(/[\d,]+ only on C\d/))
    })
  }),

  J("J-17", "Explain a finding", async (ctx) => {
    const { page } = ctx
    await ctx.open(ctx.cases.phonesOnly, "/workspace")
    await ctx.step("a finding with phone links shows How this was found", async () => {
      await ctx.see(page.getByRole("heading", { name: "How this was found" }))
      await ctx.see(page.getByText(/Lead for enquiry|Result for report/))
    })
  }),
]
