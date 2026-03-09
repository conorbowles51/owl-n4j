import { useEffect, useState } from "react"
import { Navigate, Outlet, useLocation } from "react-router-dom"
import { useAuthStore } from "../hooks/use-auth"
import { authAPI } from "../api"
import { LoadingSpinner } from "@/components/ui/loading-spinner"

export function ProtectedRoute() {
  const { isAuthenticated, user, setUser, logout } = useAuthStore()
  const [checking, setChecking] = useState(!user && isAuthenticated)
  const location = useLocation()

  useEffect(() => {
    if (isAuthenticated && !user) {
      authAPI
        .me()
        .then((u) => {
          setUser(u)
        })
        .catch(() => {
          logout()
        })
        .finally(() => setChecking(false))
    }
  }, [isAuthenticated, user, setUser, logout])

  if (checking) {
    return (
      <div className="flex h-screen items-center justify-center">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  return <Outlet />
}
