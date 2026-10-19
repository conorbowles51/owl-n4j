// Read-only documentation acceptance. Uses the existing synthetic asset case.
const path = require("path"),
  fs = require("fs");
const root = path.resolve(__dirname, "..");
const { chromium } = require(
  path.join(root, "frontend_v2/node_modules/playwright"),
);
(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({
      viewport: { width: 1440, height: 1000 },
    });
    page.setDefaultTimeout(30000);
    let writes = 0;
    await page.route("**/api/**", async (route) => {
      const r = route.request();
      if (!["GET", "HEAD"].includes(r.method()) && !/\/auth\//.test(r.url())) {
        writes++;
        await route.abort();
      } else await route.continue();
    });
    await page.goto("http://127.0.0.1:55174/login");
    await page
      .getByPlaceholder("Enter your username")
      .fill("loupe-local@example.com");
    await page
      .getByPlaceholder("Enter your password")
      .fill("Loupe-local-test-2026");
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await page.waitForURL((u) => !u.pathname.includes("login"));
    await page.goto(
      `http://127.0.0.1:55174/cases/${process.env.LOUPE_GUIDE_CASE_ID || "3dfbafe7-fa6b-4bdd-9af5-0e97975447b9"}/financial`,
    );
    const guide = page.getByRole("button", {
      name: "Financial guide",
      exact: true,
    });
    await guide.waitFor();
    const primary = [
      "Transactions",
      "Statements",
      "Findings",
      "People and businesses",
      "Transfers",
      "Patterns",
      "Trends",
    ];
    const extra = [
      "Payment graph",
      "Trace funds",
      "Payments and case events",
      "Import review",
      "Excluded transactions",
      "Processing history",
      "Change history",
    ];
    for (const name of [...primary, ...extra]) {
      if (primary.includes(name))
        await page.getByRole("tab", { name, exact: true }).click();
      else {
        await page
          .getByRole("button", { name: "More financial tools", exact: true })
          .click();
        await page.getByRole("menuitem", { name, exact: true }).click();
      }
      if (!(await guide.isVisible())) throw Error("Guide absent " + name);
      const box = await guide.boundingBox();
      if (box.y < 0 || box.y + box.height > 1000)
        throw Error("Guide outside viewport " + name);
    }
    await page.getByRole("tab", { name: "Transfers", exact: true }).click();
    await page
      .getByLabel("Transfer start date", { exact: true })
      .fill("2026-01-01");
    await guide.click();
    const dialog = page.getByRole("dialog", {
      name: "Financial user guide",
      exact: true,
    });
    await dialog
      .getByRole("heading", { name: "Loupe financial user guide", exact: true })
      .waitFor();
    const headings = await dialog.locator("article h2").allTextContents();
    const expectedChapters = fs
      .readFileSync(
        path.join(root, "docs/user-guide/financial-user-guide.md"),
        "utf8",
      )
      .split("\n")
      .filter((line) => line.startsWith("## ")).length;
    if (headings.length !== expectedChapters)
      throw Error("Expected full guide chapters");
    const bad = await dialog
      .locator('a[href^="#"]')
      .evaluateAll((links) =>
        links
          .filter((a) => !document.getElementById(a.hash.slice(1)))
          .map((a) => a.hash),
      );
    if (bad.length) throw Error("Broken contents " + bad);
    await dialog.getByRole("link", { name: "Add a PDF", exact: true }).click();
    await dialog
      .getByRole("heading", { name: "Add a PDF", exact: true })
      .waitFor();
    await dialog
      .getByRole("button", { name: "Guide contents", exact: true })
      .click();
    await page.screenshot({ path: "/tmp/loupe-guide-modal-desktop.png" });
    // A failed guide download must offer a retry without changing the case form.
    await page.route("**/docs/financial-testing/financial-team-checklist.md", route => route.fulfill({status:503,body:"Unavailable"}), {times:1});
    await dialog.getByRole("button", {name:"Testing guide",exact:true}).click();
    const testing = page.getByRole("dialog", {name:"Financial testing guide",exact:true});
    await testing.getByRole("alert").waitFor();
    await testing.getByRole("button", {name:"Retry loading guide",exact:true}).click();
    await testing.getByRole("heading", {name:"Loupe financial testing guide",exact:true}).waitFor();
    const brokenTestingLinks = await testing.locator('a[href^="#"]').evaluateAll(links => links.filter(a => !document.getElementById(a.hash.slice(1))).map(a => a.hash));
    if (brokenTestingLinks.length) throw Error("Broken testing contents: "+brokenTestingLinks);
    const testingImages = testing.locator("article img");
    if (await testingImages.count() !== 3) throw Error("Missing walkthrough images");
    for (const image of await testingImages.all()) await image.evaluate(async el => {el.loading="eager";await el.decode()});
    const pdfLink=testing.getByRole("link",{name:"checking.pdf",exact:true});
    if (await pdfLink.getAttribute("href") !== "/docs/financial-testing/checking.pdf") throw Error("Wrong sample PDF path");
    if (await pdfLink.getAttribute("target") !== "_blank") throw Error("Sample would replace the case");
    await testing.getByRole("link",{name:"Check the statement and exclude its footer",exact:true}).click();
    await page.screenshot({path:"/tmp/loupe-testing-modal-desktop.png"});
    await testing.getByRole("button",{name:"User guide",exact:true}).click();
    await page.keyboard.press("Escape");
    await dialog.waitFor({ state: "hidden" });
    if (
      (await page
        .getByLabel("Transfer start date", { exact: true })
        .inputValue()) !== "2026-01-01"
    )
      throw Error("Form lost");
    if (!(await guide.evaluate((el) => el === document.activeElement)))
      throw Error("Focus not restored");
    await page.setViewportSize({ width: 390, height: 844 });
    await guide.click();
    await dialog.waitFor();
    await page.screenshot({ path: "/tmp/loupe-guide-modal-mobile.png" });
    if (await dialog.evaluate((el) => el.scrollWidth > el.clientWidth + 1))
      throw Error("Modal overflows");
    await dialog.getByRole("button", {name:"Testing guide",exact:true}).click();
    await testing.getByRole("heading", {name:"Loupe financial testing guide",exact:true}).waitFor();
    if (await testing.evaluate(el => el.scrollWidth > el.clientWidth+1)) throw Error("Testing modal overflows");
    await page.screenshot({path:"/tmp/loupe-testing-modal-mobile.png"});
    await testing.getByRole("button",{name:"User guide",exact:true}).click();
    await dialog.getByRole("link", { name: "Add a PDF", exact: true }).click();
    const img = dialog.getByAltText("PDF upload and preparation controls");
    await img.scrollIntoViewIfNeeded();
    await img.evaluate(async (el) => {
      // Start the off-screen image request before decoding a lazily loaded image.
      el.loading = "eager";
      await el.decode();
    });
    await page.screenshot({ path: "/tmp/loupe-guide-modal-mobile-image.png" });
    await dialog.getByRole("button", { name: "Close", exact: true }).click();
    if (
      (await page
        .getByLabel("Transfer start date", { exact: true })
        .inputValue()) !== "2026-01-01"
    )
      throw Error("Form lost on narrow close");
    if (writes) throw Error("Unexpected case write");
    console.log(
      JSON.stringify({
        tabs_with_guide: 14,
        contents_links: "passed",
        desktop_mobile: "passed",
        image_loaded: true,
        escape_focus_return: true,
        unsaved_form_preserved: true,
        case_writes: writes,
        testing_guide: "contents, sample links, three images, narrow layout and failed-load retry passed",
      }),
    );
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
