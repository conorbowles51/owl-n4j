// lx-collect: the routes the cb-ux kit's Add to… calls (frontend_v2/src/features/phones/collect.api.ts).
// Red until lx-collect is live. Writes only in the training case.
import { StepFailed } from "../lib.mjs"

const J = (id, title, run) => ({ id, owner: "lx-collect", gate: "lx-collect DONE", title, run })

export default [
  J("CO-kit", "links:add answers {added, skipped} and refuses over 5,000 instead of cutting", async (ctx) => {
    const { page } = ctx
    await ctx.open(ctx.cases.training, "/dossiers")
    await ctx.step("over the limit is refused, not cut", async () => {
      const r = await page.evaluate(async () => {
        const token = localStorage.getItem("authToken") ?? ""
        const links = Array.from({ length: 5001 }, (_, i) => ({ target_type: "phone_record", target_id: `x${i}`, relationship_type: "link", label: "kit check", source_anchor: null }))
        const res = await fetch("/api/dossiers/00000000-0000-4000-8000-000000000000/links:add", {
          method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
          body: JSON.stringify({ links, origin: "journey test" }),
        })
        return res.status
      })
      if (r === 404 || r === 405) throw new StepFailed("route", `links:add answered ${r} (not live)`)
      if (r !== 413 && r !== 422) throw new StepFailed("limit", `5,001 links answered ${r}, expected a refusal`)
    })
  }),
]
