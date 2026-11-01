export interface User {
  id?: string
  email?: string
  username: string
  name: string
  role: string | null
  global_role?: string
  is_active?: boolean
  created_at?: string
  updated_at?: string
}

export interface LoginRequest {
  username: string
  password: string
}

export interface LoginResponse {
  access_token: string
  username: string
  name: string
  role: string | null
}

export interface AuthState {
  isAuthenticated: boolean
  user: User | null
  token: string | null
}

/**
 * A super admin as the server decides it (services/case_service.is_super_admin: global role super_admin). /auth/me
 * sends the global role as ``role``; a stored session may carry ``global_role``. An "admin" is not a super admin.
 */
export function isSuperAdminUser(user: Pick<User, "role" | "global_role"> | null | undefined) {
  return user?.role === "super_admin" || user?.global_role === "super_admin"
}
