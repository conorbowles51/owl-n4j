import { expect, test } from "@playwright/test"
import {
  installBrandSmokeApiMocks,
  saveBrandSmokeScreenshot,
  seedAuthenticatedSession,
} from "./fixtures/brand-smoke"

async function expectNoLegacyIdentity(page: import("@playwright/test").Page) {
  await expect(page.locator("body")).not.toContainText(/Owl|Deduce|Arclight/i)
}

test.describe("brand smoke screenshots", () => {
  test("captures the unauthenticated Loupe login redirect", async ({
    page,
  }, testInfo) => {
    await installBrandSmokeApiMocks(page, { session: "unauthenticated" })

    await page.goto("/cases")

    await expect(page).toHaveURL(/\/login$/)
    await expect(page.getByAltText("Loupe")).toBeVisible()
    await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible()
    await expectNoLegacyIdentity(page)
    await saveBrandSmokeScreenshot(page, testInfo, "login-redirect")
  })

  test("captures the Loupe login failure state", async ({ page }, testInfo) => {
    await installBrandSmokeApiMocks(page, {
      login: "failure",
      session: "unauthenticated",
    })

    await page.goto("/login")
    await page.getByLabel("Username").fill("case.lead")
    await page.getByRole("textbox", { name: "Password" }).fill("not-the-password")
    await page.getByRole("button", { name: "Sign in" }).click()

    await expect(page).toHaveURL(/\/login$/)
    await expect(page.getByRole("alert")).toContainText(
      "Invalid username or password"
    )
    await expectNoLegacyIdentity(page)
    await saveBrandSmokeScreenshot(page, testInfo, "login-failure")
  })

  test("captures the empty authenticated Loupe case workspace", async ({
    page,
  }, testInfo) => {
    await seedAuthenticatedSession(page)
    await installBrandSmokeApiMocks(page, { cases: "empty" })

    await page.goto("/cases")

    await expect(page.locator('img[src="/loupe-logo-transparent.png"]')).toBeVisible()
    await expect(page.getByText("No cases")).toBeVisible()
    await expect(page.getByText("Create a case to get started")).toBeVisible()
    await expect(page.getByText("Select a case")).toBeVisible()
    await expectNoLegacyIdentity(page)
    await saveBrandSmokeScreenshot(page, testInfo, "cases-empty")
  })

  test("captures the populated Loupe case management workspace", async ({
    page,
  }, testInfo) => {
    await seedAuthenticatedSession(page)
    await installBrandSmokeApiMocks(page)

    await page.goto("/cases")
    await page.getByText("Harbor Line Review").click()

    await expect(page.locator('img[src="/loupe-logo-transparent.png"]')).toBeVisible()
    await expect(page.getByRole("button", { name: "Open Case" })).toBeVisible()
    await expect(page.getByRole("button", { name: "Workspace" })).toBeVisible()
    await expect(page.getByText("Pilot readiness review").first()).toBeVisible()
    await expect(page.getByText("Initial case map")).toBeVisible()
    await expectNoLegacyIdentity(page)
    await saveBrandSmokeScreenshot(page, testInfo, "cases-populated")
  })
})
