import { useEffect } from "react"
import { Navigate, Outlet, useLocation } from "react-router-dom"
import { useAuthStore } from "../hooks/use-auth"
import { authAPI } from "../api"
import { LoadingSpinner } from "@/components/ui/loading-spinner"

export function ProtectedRoute() {
  const { isAuthenticated, user, setUser, logout } = useAuthStore()
  const location = useLocation()

  useEffect(() => {
    if (isAuthenticated && !user) {
      const token = localStorage.getItem("authToken")
      let active = true
      authAPI
        .me()
        .then((u) => {
          if (active && localStorage.getItem("authToken") === token) setUser(u)
        })
        .catch(() => {
          if (
            active &&
            (!localStorage.getItem("authToken") ||
              localStorage.getItem("authToken") === token)
          )
            logout()
        })
      return () => {
        active = false
      }
    }
  }, [isAuthenticated, user, setUser, logout])

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  if (!user) {
    return (
      <div className="flex h-screen items-center justify-center">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  return <Outlet />
}
