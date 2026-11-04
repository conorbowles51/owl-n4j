import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { renderHook, waitFor } from "@testing-library/react"
import type { ReactNode } from "react"
import { afterEach, expect, it, vi } from "vitest"
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

it("reads the rights members/me grants: an owner and an editor can edit, a viewer cannot", async () => {
  const answers: Record<string, unknown> = {
    owner: { case_id: "c1", user_id: "u1", membership_role: "owner", user: null, created_at: "", updated_at: "",
      added_by_user_id: "u1", permissions: { case: { view: true, edit: true, delete: true }, collaborators: { invite: true }, evidence: { upload: true } } },
    editor: { case_id: "c1", user_id: "u1", membership_role: "collaborator", user: null, created_at: "", updated_at: "",
      added_by_user_id: "u2", permissions: { case: { view: true, edit: true, delete: false }, collaborators: { invite: false }, evidence: { upload: true } } },
    viewer: { case_id: "c1", user_id: "u1", membership_role: "collaborator", user: null, created_at: "", updated_at: "",
      added_by_user_id: "u2", permissions: { case: { view: true, edit: false, delete: false }, collaborators: { invite: false }, evidence: { upload: false } } },
  }
  useAuthStore.setState({ user: { username: "u@example.test", name: "U", role: "user" } })
  const seen: Record<string, unknown> = {}
  for (const who of ["owner", "editor", "viewer"]) {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(answers[who]), { status: 200, headers: { "Content-Type": "application/json" } }))
    const { result } = renderHook(() => usePermissions("c1"), { wrapper })
    await waitFor(() => expect(fetchSpy).toHaveBeenCalled())
    await waitFor(() => expect(result.current.canUploadEvidence || who === "viewer").toBe(true))
    await new Promise((r) => setTimeout(r, 20))
    const p = result.current
    seen[who] = [p.isOwner, p.canEdit, p.canDelete, p.canInvite, p.canUploadEvidence]
    fetchSpy.mockRestore()
  }
  expect(seen).toEqual({
    owner: [true, true, true, true, true],
    editor: [false, true, false, false, true],
    viewer: [false, false, false, false, false],
  })
})
