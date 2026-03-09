import { create } from "zustand"
import type { User } from "../auth.types"

interface AuthStore {
  isAuthenticated: boolean
  user: User | null
  login: (token: string, user: User) => void
  logout: () => void
  setUser: (user: User) => void
}

export const useAuthStore = create<AuthStore>((set) => ({
  isAuthenticated: !!localStorage.getItem("authToken"),
  user: null,

  login: (token: string, user: User) => {
    localStorage.setItem("authToken", token)
    set({ isAuthenticated: true, user })
  },

  logout: () => {
    localStorage.removeItem("authToken")
    set({ isAuthenticated: false, user: null })
  },

  setUser: (user: User) => {
    set({ user, isAuthenticated: true })
  },
}))
