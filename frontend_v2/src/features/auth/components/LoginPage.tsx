import { useState } from "react"
import { useLocation, useNavigate } from "react-router-dom"
import { Eye, EyeOff, ShieldCheck } from "lucide-react"
import { LoupeLogo } from "@/components/brand/LoupeLogo"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { authAPI } from "../api"
import type { SignedIn } from "../auth.types"
import { useAuthStore } from "../hooks/use-auth"
import { ResetWithCodeForm } from "./ResetWithCodeForm"
import { SecondStepForm } from "./SecondStepForm"

function LoginBackdrop() {
  return (
    <div
      className="pointer-events-none absolute inset-0 overflow-hidden"
      aria-hidden="true"
    >
      <div className="absolute inset-0 opacity-70 [background-image:linear-gradient(hsl(var(--border)/0.48)_1px,transparent_1px),linear-gradient(90deg,hsl(var(--border)/0.48)_1px,transparent_1px)] [background-size:3.5rem_3.5rem] [mask-image:radial-gradient(ellipse_72%_70%_at_50%_48%,black_6%,transparent_78%)] dark:opacity-30" />
      <div className="absolute left-1/2 top-[46%] size-[38rem] -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary/[0.065] blur-[120px] dark:bg-primary/[0.055]" />
      <div className="absolute left-1/2 top-[46%] size-[44rem] -translate-x-1/2 -translate-y-1/2 rounded-full border border-primary/[0.08] dark:border-primary/[0.07]" />
      <div className="absolute left-1/2 top-[46%] size-[31rem] -translate-x-1/2 -translate-y-1/2 rounded-full border border-primary/[0.065] dark:border-primary/[0.055]" />
      <div className="absolute left-1/2 top-[46%] size-[18rem] -translate-x-1/2 -translate-y-1/2 rounded-full border border-primary/[0.055] dark:border-primary/[0.045]" />
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
  const [secondStepToken, setSecondStepToken] = useState<string | null>(null)
  const [resetting, setResetting] = useState(false)
  const [notice, setNotice] = useState("")
  const login = useAuthStore((state) => state.login)
  const navigate = useNavigate()
  const location = useLocation()

  const finishSignIn = (response: SignedIn) => {
    login({
      username: response.username,
      name: response.name,
      role: response.role,
    })
    if (response.two_step_setup_required) {
      navigate("/settings/security", { replace: true })
      return
    }
    const from = location.state?.from
    const path = from?.pathname
    const returnTo =
      typeof path === "string" &&
      path.startsWith("/") &&
      !path.startsWith("//") &&
      !path.includes("\\") &&
      !/^\/login(?:\/|$)/.test(path)
        ? path +
          (typeof from.search === "string" && from.search.startsWith("?")
            ? from.search
            : "") +
          (typeof from.hash === "string" && from.hash.startsWith("#")
            ? from.hash
            : "")
        : "/cases"
    navigate(returnTo, { replace: true })
  }

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    setError("")
    setNotice("")
    setLoading(true)

    try {
      const response = await authAPI.login({ username, password })
      if ("two_step_required" in response) {
        setSecondStepToken(response.two_step_token)
      } else {
        finishSignIn(response)
      }
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

      <main id="login-content" className="relative z-10 w-full max-w-[25rem]">
        <div className="flex justify-center">
          <LoupeLogo size="login" />
        </div>

        <section
          className="relative mt-7 overflow-hidden rounded-xl border border-border/80 bg-card/85 p-6 shadow-xl backdrop-blur-xl dark:bg-card/78 sm:p-7"
          aria-labelledby="login-heading"
        >
          <div className="absolute inset-x-8 top-0 h-px bg-gradient-to-r from-transparent via-primary/65 to-transparent" />
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

          {secondStepToken ? (
            <SecondStepForm
              token={secondStepToken}
              onSignedIn={finishSignIn}
              onCancel={() => {
                setSecondStepToken(null)
                setPassword("")
              }}
            />
          ) : resetting ? (
            <ResetWithCodeForm
              initialEmail={username}
              onDone={(message) => {
                setResetting(false)
                setPassword("")
                setNotice(message)
              }}
              onCancel={() => setResetting(false)}
            />
          ) : (
          <form onSubmit={handleSubmit} className="mt-7 space-y-5">
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
                className="h-11 bg-background/90 shadow-sm dark:bg-background/55"
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
                  className="h-11 bg-background/90 pr-11 shadow-sm dark:bg-background/55"
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

            {notice && (
              <div
                role="status"
                className="rounded-md border border-emerald-200 bg-emerald-50 px-3.5 py-2.5 text-xs leading-5 text-emerald-800 dark:border-emerald-500/20 dark:bg-emerald-500/10 dark:text-emerald-300"
              >
                {notice}
              </div>
            )}

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

            <button
              type="button"
              className="block w-full text-center text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
              onClick={() => {
                setError("")
                setResetting(true)
              }}
            >
              I have a reset code
            </button>
          </form>
          )}

          <div className="mt-7 flex items-start justify-center gap-2.5 border-t border-border pt-5">
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
