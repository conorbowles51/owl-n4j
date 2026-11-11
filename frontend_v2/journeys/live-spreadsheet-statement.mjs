// Live check for the spreadsheet statement reader (followups batch 94): signed in with the jobs login over plain
// http, on the demo case it owns. The Penn CSV is put in Financial (the same request the Evidence picker sends),
// then read and stored through the screen: Read as a statement, the mapping, the skipped lines, Add to ledger.
// Usage: node journeys/live-spreadsheet-statement.mjs <shots dir> [--store]
import { chromium } from "playwright"
import { CASES, readLogin, signIn } from "./lib.mjs"

const C = CASES.demo
const FILE = "penn-used-tools-old-ferrow-2024.csv"
const shots = process.argv[2] || "/tmp"
const store = process.argv.includes("--store")
const login = readLogin()
const browser = await chromium.launch()
const out = {}
try {
  const { page } = await signIn(browser, login)
  const api = (path, body) => page.evaluate(async ([p, b]) => {
    const r = await fetch(p, b ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) } : {})
    return { status: r.status, body: await r.json().catch(() => null) }
  }, [path, body])
  // The demo case's Penn CSV (evidence file id read from the case, 11 Nov).
  const penn = { id: process.env.PENN_FILE_ID || "c677baf6-dc8c-4499-ae0b-8f2267936aa8" }
  out.file = penn.id
  const resolved = await api(`/api/financial/statement-import/selection/resolve?case_id=${C}`,
    { file_ids: [penn.id], folder_ids: [], include_other_formats: true })
  const chosen = resolved.body?.files?.find((f) => f.id === penn.id)
  out.resolve = resolved.status
  if (chosen && chosen.financial_removed !== true) {
    const inc = await api(`/api/financial/statement-import/selection/include?case_id=${C}`,
      { files: [{ evidence_file_id: penn.id, expected_revision: chosen.financial_visibility_revision }] })
    out.include = inc.status
  }
  await page.goto(`${login.url}/cases/${C}/financial?view=statements&files=1`, { waitUntil: "domcontentloaded" })
  const card = page.getByRole("article", { name: `Financial source ${FILE}` })
  await card.waitFor({ timeout: 90000 })
  await card.scrollIntoViewIfNeeded()
  await page.screenshot({ path: `${shots}/1-source-card.png` })
  out.card_text = (await card.innerText()).replace(/\s+/g, " ").slice(0, 300)
  await card.getByTestId("read-spreadsheet-statement").click()
  await page.getByTestId("window-start").fill("2023-01-01")
  await page.getByTestId("window-end").fill("2024-12-31")
  await page.getByTestId("default-currency").fill("USD")
  await page.getByTestId("read-file").click()
  await page.getByTestId("spreadsheet-mapping").waitFor({ timeout: 120000 })
  out.rows = await page.getByTestId("precheck-rows").innerText()
  out.mapping_source = await page.getByTestId("mapping-source").innerText()
  out.mapping = []
  for (let c = 0; c < 4; c++) out.mapping.push(await page.getByTestId(`mapping-column-${c}`).inputValue())
  out.named_spreadsheet_statement = (await page.getByTestId("precheck-report").getByText("Spreadsheet statement").count()) > 0
  const held = page.getByTestId("already-in-ledger")
  out.already_in_ledger = (await held.count()) ? (await held.innerText()).replace(/\s+/g, " ") : null
  out.add_offered = (await page.getByTestId("store-file").count()) > 0
  out.uuid_available = await page.evaluate(() => typeof crypto.randomUUID)
  await page.screenshot({ path: `${shots}/2-mapping.png`, fullPage: true })
  if (store && out.add_offered) {
    await page.getByTestId("store-file").click()
    await page.getByTestId("ingest-report").waitFor({ timeout: 180000 })
    out.stored = (await page.getByTestId("ingest-report").innerText()).replace(/\s+/g, " ")
    await page.screenshot({ path: `${shots}/3-stored.png` })
  }
} catch (e) {
  out.error = String(e).slice(0, 400)
  try {
    const pages = browser.contexts().flatMap((c) => c.pages())
    if (pages[0]) {
      await pages[0].screenshot({ path: `${shots}/0-failed.png`, fullPage: true })
      out.url = pages[0].url()
      out.articles = await pages[0].getByRole("article").evaluateAll((els) => els.map((e) => e.getAttribute("aria-label")).slice(0, 40))
    }
  } catch (s) { out.shot_error = String(s).slice(0, 200) }
} finally {
  await browser.close()
  console.log(JSON.stringify(out, null, 1))
}
