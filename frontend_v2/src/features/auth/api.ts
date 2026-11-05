import { fetchAPI } from "@/lib/api-client"
import type {
  LoginRequest,
  LoginResponse,
  SignedIn,
  TwoStepStart,
  TwoStepStatus,
  User,
} from "./auth.types"

export const authAPI = {
  login: (data: LoginRequest) =>
    fetchAPI<LoginResponse>("/api/auth/login", {
      method: "POST",
      body: data,
    }),

  loginSecondStep: (token: string, code: string) =>
    fetchAPI<SignedIn>("/api/auth/login/second-step", {
      method: "POST",
      body: { two_step_token: token, code },
    }),

  resetWithCode: (email: string, code: string, newPassword: string) =>
    fetchAPI<void>("/api/auth/reset-with-code", {
      method: "POST",
      body: { email, code, new_password: newPassword },
    }),

  twoStepStatus: () => fetchAPI<TwoStepStatus>("/api/auth/two-step"),

  twoStepStart: (password: string) =>
    fetchAPI<TwoStepStart>("/api/auth/two-step/start", {
      method: "POST",
      body: { password },
    }),

  twoStepConfirm: (code: string) =>
    fetchAPI<{ recovery_codes: string[] }>("/api/auth/two-step/confirm", {
      method: "POST",
      body: { code },
    }),

  twoStepNewRecoveryCodes: (password: string, code: string) =>
    fetchAPI<{ recovery_codes: string[] }>("/api/auth/two-step/recovery-codes", {
      method: "POST",
      body: { password, code },
    }),

  twoStepTurnOff: (password: string, code: string) =>
    fetchAPI<void>("/api/auth/two-step/turn-off", {
      method: "POST",
      body: { password, code },
    }),

  logout: () =>
    fetchAPI<void>("/api/auth/logout", {
      method: "POST",
    }),

  me: () => fetchAPI<User>("/api/auth/me"),

  getUsers: () =>
    fetchAPI<{ users: User[]; total: number }>("/api/users").then(
      (r) => r.users
    ),

  // Changing the password ends every other sign-in; this one continues with the cookie the reply sets.
  changePassword: (currentPassword: string, newPassword: string) =>
    fetchAPI<void>("/api/auth/change-password", {
      method: "PUT",
      body: { current_password: currentPassword, new_password: newPassword },
    }),
}
