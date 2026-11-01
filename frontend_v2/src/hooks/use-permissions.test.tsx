import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { renderHook } from "@testing-library/react"
import type { ReactNode } from "react"
import { afterEach, expect, it } from "vitest"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import { useCasePermissions } from "@/features/cases/hooks/use-case-permissions"
import type { Case } from "@/types/case.types"
import { usePermissions } from "./use-permissions"

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>
)
const someoneElsesCase = { id: "c1", is_owner: false, user_role: "viewer" } as unknown as Case

afterEach(() => useAuthStore.setState({ user: null }))

it("both permission hooks agree with the server about who is a super admin", () => {
  for (const [role, superAdmin] of [["super_admin", true], ["admin", false], ["user", false]] as const) {
    useAuthStore.setState({ user: { username: "u@example.test", name: "U", role } })
    const plain = renderHook(() => usePermissions(undefined), { wrapper }).result.current
    const forCase = renderHook(() => useCasePermissions(someoneElsesCase)).result.current
    expect([role, plain.isSuperAdmin]).toEqual([role, superAdmin])
    expect([role, forCase.isSuperAdmin]).toEqual([role, superAdmin])
    expect(plain.canDelete).toBe(forCase.canDelete)
  }
})
