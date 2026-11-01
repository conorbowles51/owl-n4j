#!/usr/bin/env node
// Live journey runner (07 section 10.1 [S]): node journeys/run.mjs [--owner cb-screens] [--id J-2] [--out file.json]
// Signs in once with the jobs login, runs each journey serially on the synthetic cases, and prints one line per
// journey: id, owner, passed or the failed step, time and actions. Never prints page text or the password.
// Run niced and under the suite lock:  nice -n 15 flock /mnt/owl-data/fin-wt/suite.lock node journeys/run.mjs
import { writeFileSync } from "node:fs"
import { chromium } from "playwright"
import { StepFailed, context, readLogin, signIn } from "./lib.mjs"
import { ALL } from "./specs/index.mjs"

const arg = (name) => {
  const i = process.argv.indexOf(`--${name}`)
  return i > 0 ? process.argv[i + 1] : undefined
}
const owner = arg("owner")
const only = arg("id")
const out = arg("out")
const chosen = ALL.filter((j) => (!owner || j.owner === owner) && (!only || j.id === only))
if (!chosen.length) {
  console.error("no journeys match")
  process.exit(2)
}

const login = readLogin()
const browser = await chromium.launch()
const results = []
try {
  const { context: browserContext } = await signIn(browser, login)
  for (const journey of chosen) {
    const page = await browserContext.newPage()
    const ctx = context(page, login.url, journey)
    let line
    try {
      await journey.run(ctx)
      line = { ...ctx.result(), passed: true }
    } catch (e) {
      const failed = e instanceof StepFailed ? e : new StepFailed("run", String(e?.message ?? e).split("\n")[0].slice(0, 200))
      line = { ...ctx.result(), passed: false, failed_step: failed.step, detail: failed.detail }
    }
    results.push(line)
    console.log(`${line.passed ? "PASS" : "FAIL"} ${line.id} (${line.owner}) ${line.passed ? "" : `at "${line.failed_step}": ${line.detail}`} [${line.ms} ms, ${line.actions} actions]`)
    await page.close()
  }
} finally {
  await browser.close()
}
if (out) writeFileSync(out, JSON.stringify({ at: new Date().toISOString(), results }, null, 1))
const failed = results.filter((r) => !r.passed).length
console.log(`${results.length - failed} passed, ${failed} failed of ${results.length}`)
process.exit(failed ? 1 : 0)
