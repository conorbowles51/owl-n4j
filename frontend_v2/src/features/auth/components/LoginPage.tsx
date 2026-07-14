import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { Eye, EyeOff, ShieldCheck } from "lucide-react"
import { LoupeLogo } from "@/components/brand/LoupeLogo"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { authAPI } from "../api"
import { useAuthStore } from "../hooks/use-auth"

function LoginBackdrop() {
  return (
    <div
      className="pointer-events-none absolute inset-0 overflow-hidden"
      aria-hidden="true"
    >
      <div className="absolute inset-0 opacity-70 [background-image:linear-gradient(hsl(var(--border)/0.46)_1px,transparent_1px),linear-gradient(90deg,hsl(var(--border)/0.46)_1px,transparent_1px)] [background-size:3.5rem_3.5rem] [mask-image:radial-gradient(ellipse_70%_68%_at_50%_50%,black_8%,transparent_76%)] dark:opacity-35" />
      <div className="absolute left-1/2 top-1/2 size-[36rem] -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary/[0.035] blur-[110px] dark:bg-primary/[0.025]" />
      <div className="absolute left-1/2 top-1/2 size-[42rem] -translate-x-1/2 -translate-y-1/2 rounded-full border border-primary/[0.055] dark:border-primary/[0.045]" />
      <div className="absolute left-1/2 top-1/2 size-[30rem] -translate-x-1/2 -translate-y-1/2 rounded-full border border-primary/[0.05] dark:border-primary/[0.04]" />
      <div className="absolute left-1/2 top-1/2 size-[18rem] -translate-x-1/2 -translate-y-1/2 rounded-full border border-primary/[0.045] dark:border-primary/[0.035]" />
      <div className="absolute inset-x-0 bottom-0 h-32 bg-gradient-to-t from-background to-transparent" />
    </div>
  )
}

export function LoginPage() {
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)
  const login = useAuthStore((state) => state.login)
  const navigate = useNavigate()

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    setError("")
    setLoading(true)

    try {
      const response = await authAPI.login({ username, password })
      login(response.access_token, {
        username: response.username,
        name: response.name,
        role: response.role,
      })
      navigate("/cases")
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Login failed. Please try again."
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="relative flex min-h-dvh items-center justify-center overflow-hidden bg-background px-6 py-10 text-foreground sm:px-8">
      <LoginBackdrop />

      <main
        id="login-content"
        className="relative z-10 w-full max-w-[25rem]"
      >
        <div className="flex justify-center">
          <LoupeLogo size="login" />
        </div>

        <section className="mt-9" aria-labelledby="login-heading">
          <header className="text-center">
            <h1
              id="login-heading"
              className="text-3xl font-semibold tracking-[-0.035em] text-foreground"
            >
              Welcome back
            </h1>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              Sign in to continue to your investigation workspace.
            </p>
          </header>

          <form onSubmit={handleSubmit} className="mt-8 space-y-5">
            <div className="space-y-2">
              <label
                htmlFor="username"
                className="block text-[13px] font-semibold text-foreground"
              >
                Username
              </label>
              <Input
                id="username"
                type="text"
                placeholder="Enter your username"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                autoComplete="username"
                disabled={loading}
                aria-invalid={Boolean(error)}
                className="h-11 bg-card/95 shadow-[0_8px_22px_rgba(7,24,32,0.035)] dark:shadow-none"
              />
            </div>

            <div className="space-y-2">
              <label
                htmlFor="password"
                className="block text-[13px] font-semibold text-foreground"
              >
                Password
              </label>
              <div className="relative">
                <Input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  placeholder="Enter your password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  autoComplete="current-password"
                  disabled={loading}
                  aria-invalid={Boolean(error)}
                  className="h-11 bg-card/95 pr-11 shadow-[0_8px_22px_rgba(7,24,32,0.035)] dark:shadow-none"
                />
                <button
                  type="button"
                  tabIndex={-1}
                  className="absolute right-3 top-1/2 flex size-7 -translate-y-1/2 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                  onClick={() => setShowPassword((visible) => !visible)}
                  aria-label={showPassword ? "Hide password" : "Show password"}
                >
                  {showPassword ? (
                    <EyeOff className="size-4" />
                  ) : (
                    <Eye className="size-4" />
                  )}
                </button>
              </div>
            </div>

            {error && (
              <div
                role="alert"
                className="rounded-md border border-red-200 bg-red-50 px-3.5 py-2.5 text-xs leading-5 text-red-700 dark:border-red-500/20 dark:bg-red-500/10 dark:text-red-300"
              >
                {error}
              </div>
            )}

            <Button
              type="submit"
              variant="primary"
              size="lg"
              className="h-11 w-full"
              disabled={loading || !username || !password}
            >
              {loading ? (
                <>
                  <LoadingSpinner size="sm" />
                  Signing in
                </>
              ) : (
                "Sign in"
              )}
            </Button>
          </form>

          <div className="mt-8 flex items-start justify-center gap-2.5 border-t border-border pt-5">
            <ShieldCheck
              className="mt-0.5 size-4 shrink-0 text-primary"
              strokeWidth={1.7}
            />
            <p className="max-w-xs text-xs leading-5 text-muted-foreground">
              Access is logged and monitored. Unauthorized use is prohibited.
            </p>
          </div>
        </section>

        <p className="mt-8 text-center text-[11px] text-muted-foreground">
          &copy; {new Date().getFullYear()} Loupe
        </p>
      </main>
    </div>
  )
}
