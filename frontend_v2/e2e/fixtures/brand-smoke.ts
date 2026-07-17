import type { Page, Route, TestInfo } from "@playwright/test"
import type { User } from "../../src/features/auth/auth.types"
import type { Snapshot } from "../../src/features/cases/snapshots-api"
import type { Case, CaseDeadline } from "../../src/types/case.types"

export const brandSmokeToken = "brand-smoke-token"

export const brandSmokeUser: User = {
  id: "user-brand-smoke",
  email: "case.lead@example.test",
  username: "case.lead",
  name: "Case Lead",
  role: "admin",
  global_role: "admin",
  is_active: true,
  created_at: "2026-07-16T09:00:00Z",
  updated_at: "2026-07-16T09:00:00Z",
}

export const brandSmokeCases: Case[] = [
  {
    id: "case-loupe-001",
    title: "Harbor Line Review",
    description: "Story fixture for validating the release candidate identity.",
    created_by_user_id: brandSmokeUser.id!,
    owner_user_id: brandSmokeUser.id!,
    created_at: "2026-07-14T09:20:00Z",
    updated_at: "2026-07-16T17:45:00Z",
    owner_name: "Case Lead",
    user_role: "owner",
    is_owner: true,
    archived: false,
    next_deadline_date: "2026-07-24",
    next_deadline_name: "Pilot readiness review",
  },
  {
    id: "case-loupe-002",
    title: "North Pier Timeline",
    description: "Viewer role fixture for list-level permission smoke coverage.",
    created_by_user_id: "user-secondary",
    owner_user_id: "user-secondary",
    created_at: "2026-07-11T10:00:00Z",
    updated_at: "2026-07-15T12:30:00Z",
    owner_name: "Review Partner",
    user_role: "viewer",
    is_owner: false,
    archived: false,
    next_deadline_date: null,
    next_deadline_name: null,
  },
]

export const brandSmokeDeadlines: CaseDeadline[] = [
  {
    id: "deadline-pilot-review",
    case_id: "case-loupe-001",
    name: "Pilot readiness review",
    due_date: "2026-07-24",
    created_by_user_id: brandSmokeUser.id!,
    created_at: "2026-07-14T09:30:00Z",
    updated_at: "2026-07-14T09:30:00Z",
  },
]

export const brandSmokeSnapshots: Snapshot[] = [
  {
    id: "snapshot-initial-map",
    name: "Initial case map",
    notes: "Baseline graph state for release smoke evidence.",
    timestamp: "2026-07-16T15:10:00Z",
    node_count: 18,
    link_count: 27,
    timeline_count: 6,
    created_at: "2026-07-16T15:10:00Z",
    ai_overview: "Core people, places, and transactions are linked for review.",
    case_id: "case-loupe-001",
    case_version: "v1",
    case_name: "Harbor Line Review",
  },
]

export type BrandSmokeCaseMode = "success" | "empty" | "failure"
export type BrandSmokeLoginMode = "success" | "failure"
export type BrandSmokeSessionMode = "authenticated" | "unauthenticated"

interface BrandSmokeApiOptions {
  cases?: BrandSmokeCaseMode
  login?: BrandSmokeLoginMode
  session?: BrandSmokeSessionMode
}

async function fulfillJson(route: Route, status: number, body: unknown) {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  })
}

function hasBearerToken(route: Route) {
  return Boolean(route.request().headers().authorization)
}

export async function seedAuthenticatedSession(page: Page) {
  await page.addInitScript((token) => {
    window.localStorage.setItem("authToken", token)
  }, brandSmokeToken)
}

export async function installBrandSmokeApiMocks(
  page: Page,
  options: BrandSmokeApiOptions = {}
) {
  const {
    cases = "success",
    login = "success",
    session = "authenticated",
  } = options

  await page.route("**/api/**", async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const method = request.method()

    if (method === "POST" && url.pathname === "/api/auth/login") {
      if (login === "failure") {
        await fulfillJson(route, 401, { detail: "Invalid username or password" })
        return
      }

      await fulfillJson(route, 200, {
        access_token: brandSmokeToken,
        username: brandSmokeUser.username,
        name: brandSmokeUser.name,
        role: brandSmokeUser.role,
      })
      return
    }

    if (method === "GET" && url.pathname === "/api/auth/me") {
      if (session === "unauthenticated" || !hasBearerToken(route)) {
        await fulfillJson(route, 401, { detail: "Not authenticated" })
        return
      }

      await fulfillJson(route, 200, brandSmokeUser)
      return
    }

    if (method === "GET" && url.pathname === "/api/cases") {
      if (cases === "failure") {
        await fulfillJson(route, 500, { detail: "Cases fixture unavailable" })
        return
      }

      const rows = cases === "empty" ? [] : brandSmokeCases
      await fulfillJson(route, 200, { cases: rows, total: rows.length })
      return
    }

    const deadlinesMatch = url.pathname.match(/^\/api\/cases\/([^/]+)\/deadlines$/)
    if (method === "GET" && deadlinesMatch) {
      const caseId = deadlinesMatch[1]
      const rows = brandSmokeDeadlines.filter((deadline) => deadline.case_id === caseId)
      await fulfillJson(route, 200, { deadlines: rows, total: rows.length })
      return
    }

    const caseMatch = url.pathname.match(/^\/api\/cases\/([^/]+)$/)
    if (method === "GET" && caseMatch) {
      const caseData = brandSmokeCases.find((row) => row.id === caseMatch[1])
      if (!caseData) {
        await fulfillJson(route, 404, { detail: "Case not found" })
        return
      }

      await fulfillJson(route, 200, caseData)
      return
    }

    if (method === "GET" && url.pathname === "/api/snapshots") {
      await fulfillJson(route, 200, brandSmokeSnapshots)
      return
    }

    await fulfillJson(route, 404, {
      detail: `No brand smoke fixture for ${method} ${url.pathname}`,
    })
  })
}

export async function saveBrandSmokeScreenshot(
  page: Page,
  testInfo: TestInfo,
  name: string
) {
  await page.screenshot({
    path: testInfo.outputPath(`brand-smoke-${name}.png`),
    fullPage: true,
  })
}
