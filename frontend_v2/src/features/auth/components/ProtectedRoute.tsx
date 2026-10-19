import { useEffect, useState } from "react"
import { Navigate, Outlet, useLocation } from "react-router-dom"
import { useAuthStore } from "../hooks/use-auth"
import { authAPI } from "../api"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { Button } from "@/components/ui/button"
import { ApiError } from "@/lib/api-client"

export function ProtectedRoute() {
  const { isAuthenticated, user, setUser, logout } = useAuthStore()
  const location = useLocation()
  const [retry, setRetry] = useState(0)
  const [profileError, setProfileError] = useState<{
    token: string | null
  } | null>(null)

  useEffect(() => {
    if (isAuthenticated && !user) {
      const token = localStorage.getItem("authToken")
      let active = true
      authAPI
        .me()
        .then((u) => {
          if (active && localStorage.getItem("authToken") === token) setUser(u)
        })
        .catch((error: unknown) => {
          const currentToken = localStorage.getItem("authToken")
          if (!active || (currentToken && currentToken !== token)) return
          if (
            !currentToken ||
            (error instanceof ApiError && [401, 403].includes(error.status))
          ) {
            logout()
          } else {
            // A failed connection does not establish that this sign-in expired.
            // Keep private pages closed until a retry confirms the profile.
            setProfileError({ token })
          }
        })
      return () => {
        active = false
      }
    }
  }, [isAuthenticated, user, setUser, logout, retry])

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  if (!user) {
    if (
      profileError &&
      profileError.token === localStorage.getItem("authToken")
    ) {
      return (
        <main className="flex min-h-screen items-center justify-center p-6">
          <section
            className="w-full max-w-md space-y-4 rounded border bg-card p-6"
            aria-labelledby="sign-in-check-title"
          >
            <h1 id="sign-in-check-title" className="text-lg font-semibold">
              Cannot check sign-in
            </h1>
            <p role="alert">
              Loupe could not check your sign-in with the server. Check your
              connection and try again.
            </p>
            <div className="flex flex-wrap gap-2">
              <Button
                onClick={() => {
                  setProfileError(null)
                  setRetry((value) => value + 1)
                }}
              >
                Retry connection
              </Button>
              <Button variant="outline" onClick={logout}>
                Sign in again
              </Button>
            </div>
          </section>
        </main>
      )
    }
    return (
      <div className="flex h-screen items-center justify-center">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  return <Outlet />
}
