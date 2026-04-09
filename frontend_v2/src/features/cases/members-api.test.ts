import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { caseMembersAPI } from "./members-api"

describe("caseMembersAPI.list", () => {
  const originalFetch = globalThis.fetch

  beforeEach(() => {
    globalThis.fetch = vi.fn()
    localStorage.clear()
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
  })

  it("maps wrapped backend member responses into the collaborator UI shape", async () => {
    vi.mocked(globalThis.fetch).mockResolvedValue(
      new Response(
        JSON.stringify({
          members: [
            {
              case_id: "case-1",
              user_id: "user-1",
              membership_role: "collaborator",
              permissions: {
                evidence: {
                  upload: true,
                },
              },
              added_by_user_id: "owner-1",
              created_at: "2026-04-09T09:00:00Z",
              updated_at: "2026-04-09T09:00:00Z",
              user: {
                id: "user-1",
                email: "editor@example.com",
                name: "Editor User",
              },
            },
          ],
          total: 1,
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }
      )
    )

    const members = await caseMembersAPI.list("case-1")

    expect(members).toEqual([
      {
        user_id: "user-1",
        user_name: "Editor User",
        user_email: "editor@example.com",
        preset: "editor",
        permissions: {
          evidence: {
            upload: true,
          },
        },
        joined_at: "2026-04-09T09:00:00Z",
      },
    ])
  })
})
