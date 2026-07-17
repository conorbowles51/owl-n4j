import type { ReactNode } from "react"
import { renderHook, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { usePermissions } from "../use-permissions"
import { caseMembersAPI } from "@/features/cases/members-api"
import { useAuthStore } from "@/features/auth/hooks/use-auth"

const mocks = vi.hoisted(() => ({
  getMyMembership: vi.fn(),
}))

vi.mock("@/features/cases/members-api", () => ({
  caseMembersAPI: {
    getMyMembership: mocks.getMyMembership,
  },
}))

function wrapper({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
}

describe("usePermissions", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAuthStore.setState({
      isAuthenticated: true,
      user: {
        username: "investigator",
        name: "Investigator",
        role: "user",
      },
    })
  })

  it("derives edit access from the mapped current membership preset", async () => {
    vi.mocked(caseMembersAPI.getMyMembership).mockResolvedValue({
      user_id: "user-1",
      user_name: "Investigator",
      user_email: "investigator@example.com",
      preset: "editor",
      permissions: { evidence: { upload: true } },
      joined_at: "2026-07-16T10:00:00Z",
    })

    const { result } = renderHook(() => usePermissions("case-1"), { wrapper })

    await waitFor(() => expect(result.current.canEdit).toBe(true))
    expect(result.current.canUploadEvidence).toBe(true)
    expect(caseMembersAPI.getMyMembership).toHaveBeenCalledWith("case-1")
  })

  it("allows super admins without a case membership response", () => {
    useAuthStore.setState({
      isAuthenticated: true,
      user: {
        username: "admin",
        name: "Admin",
        role: "super_admin",
        global_role: "super_admin",
      },
    })

    const { result } = renderHook(() => usePermissions(undefined), { wrapper })

    expect(result.current.canEdit).toBe(true)
    expect(result.current.isSuperAdmin).toBe(true)
    expect(caseMembersAPI.getMyMembership).not.toHaveBeenCalled()
  })
})
