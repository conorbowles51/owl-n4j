import { create } from "zustand"
import { queryClient } from "@/lib/query-client"
import { clearSessionMark, markSignedIn, sessionMark } from "@/lib/session-mark"
import type { User } from "../auth.types"

interface AuthStore {
  isAuthenticated: boolean
  user: User | null
  login: (user: User) => void
  logout: () => void
  setUser: (user: User) => void
}

export const useAuthStore = create<AuthStore>((set, get) => ({
  isAuthenticated: !!sessionMark(),
  user: null,

  login: (user: User) => {
    queryClient.clear()
    markSignedIn()
    set({ isAuthenticated: true, user })
  },

  logout: () => {
    queryClient.clear()
    clearSessionMark()
    set({ isAuthenticated: false, user: null })
  },

  setUser: (user: User) => {
    const previous = get().user
    if (previous && previous.username !== user.username) queryClient.clear()
    set({ user, isAuthenticated: true })
  },
}))
