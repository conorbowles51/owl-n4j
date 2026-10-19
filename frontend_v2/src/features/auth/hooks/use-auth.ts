import { create } from "zustand"
import { queryClient } from "@/lib/query-client"
import type { User } from "../auth.types"

interface AuthStore {
  isAuthenticated: boolean
  user: User | null
  login: (token: string, user: User) => void
  logout: () => void
  setUser: (user: User) => void
}

export const useAuthStore = create<AuthStore>((set, get) => ({
  isAuthenticated: !!localStorage.getItem("authToken"),
  user: null,

  login: (token: string, user: User) => {
    queryClient.clear()
    localStorage.setItem("authToken", token)
    set({ isAuthenticated: true, user })
  },

  logout: () => {
    queryClient.clear()
    localStorage.removeItem("authToken")
    set({ isAuthenticated: false, user: null })
  },

  setUser: (user: User) => {
    const previous = get().user
    if (previous && previous.username !== user.username) queryClient.clear()
    set({ user, isAuthenticated: true })
  },
}))
