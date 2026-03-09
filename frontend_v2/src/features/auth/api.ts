import { fetchAPI } from "@/lib/api-client"
import type { LoginRequest, LoginResponse, User } from "./auth.types"

export const authAPI = {
  login: (data: LoginRequest) =>
    fetchAPI<LoginResponse>("/api/auth/login", {
      method: "POST",
      body: data,
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

  changePassword: (currentPassword: string, newPassword: string) =>
    fetchAPI<void>("/api/auth/change-password", {
      method: "PUT",
      body: { current_password: currentPassword, new_password: newPassword },
    }),
}
