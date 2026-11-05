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

export interface SignedIn {
  access_token: string
  username: string
  name: string
  role: string | null
  /** An administrator who must turn on two-step sign-in before the administrator screens answer. */
  two_step_setup_required?: boolean
}

/** The password was right and this person has two-step sign-in: nothing is open until the code. */
export interface SecondStepNeeded {
  two_step_required: true
  two_step_token: string
  username: string
}

export type LoginResponse = SignedIn | SecondStepNeeded

export interface TwoStepStatus {
  enrolled: boolean
  enrolled_at: string | null
  recovery_codes_left: number
  /** Why this server cannot enrol anyone yet, or null. */
  unavailable_reason: string | null
  required: boolean
}

export interface TwoStepStart {
  secret: string
  uri: string
  /** The QR code as rows of 0 and 1, dark being 1. */
  qr: string[]
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

/** May open the admin screens: the two global roles the server's require_admin accepts. */
export function isAdminUser(user: Pick<User, "role" | "global_role"> | null | undefined) {
  return [user?.role, user?.global_role].some((role) => role === "admin" || role === "super_admin")
}
