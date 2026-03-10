import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { authAPI } from "../api"
import { useAuthStore } from "../hooks/use-auth"
import {
  Eye,
  EyeOff,
  Shield,
  Network,
  Search,
  Lock,
} from "lucide-react"
import { AnimatedGraphBackground } from "./AnimatedGraphBackground"

export function LoginPage() {
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)
  const login = useAuthStore((s) => s.login)
  const navigate = useNavigate()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    setLoading(true)

    try {
      const res = await authAPI.login({ username, password })
      login(res.access_token, {
        username: res.username,
        name: res.name,
        role: res.role,
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
    <div className="flex min-h-screen bg-background">
      {/* ── Left: Brand hero area ── */}
      <div className="relative hidden flex-1 overflow-hidden lg:flex lg:flex-col">
        {/* Background with subtle graph pattern */}
        <div className="absolute inset-0 bg-gradient-to-br from-slate-50 via-white to-slate-100 dark:from-slate-950 dark:via-slate-900 dark:to-slate-950" />

        {/* Decorative grid dots */}
        <div
          className="absolute inset-0 opacity-[0.04]"
          style={{
            backgroundImage:
              "radial-gradient(circle, hsl(210 40% 96%) 1px, transparent 1px)",
            backgroundSize: "32px 32px",
          }}
        />

        {/* Animated graph visualization */}
        <AnimatedGraphBackground />

        {/* Ambient glow */}
        <div className="absolute left-1/2 top-1/3 h-[500px] w-[500px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-amber-500/[0.04] blur-[120px]" />

        {/* Content */}
        <div className="relative z-10 flex flex-1 flex-col justify-between px-12 py-10 xl:px-20">
          {/* Top: Logo */}
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-amber-500/10 ring-1 ring-amber-500/20">
              <span className="text-lg font-bold tracking-tight text-amber-500">
                O
              </span>
            </div>
            <div>
              <span className="text-lg font-semibold tracking-tight text-slate-900 dark:text-slate-50">
                OWL
              </span>
              <span className="ml-2 text-xs font-medium tracking-widest text-slate-400 dark:text-slate-500 uppercase">
                Investigation Console
              </span>
            </div>
          </div>

          {/* Center: Hero copy */}
          <div className="max-w-lg space-y-8">
            <div className="space-y-4">
              <h1 className="text-4xl font-bold leading-tight tracking-tight text-slate-900 dark:text-slate-50">
                Uncover connections.
                <br />
                <span className="text-amber-500">Solve faster.</span>
              </h1>
              <p className="text-base leading-relaxed text-slate-500 dark:text-slate-400">
                Graph-powered investigation platform for analysts, investigators,
                and intelligence teams. Map entities, trace relationships, and
                surface hidden patterns across complex cases.
              </p>
            </div>

            {/* Feature pills */}
            <div className="grid grid-cols-2 gap-3">
              <FeaturePill
                icon={<Network className="size-4 text-node-person" />}
                label="Graph Analysis"
                description="Entity relationship mapping"
              />
              <FeaturePill
                icon={<Search className="size-4 text-amber-500" />}
                label="AI-Powered Search"
                description="Natural language queries"
              />
              <FeaturePill
                icon={<Shield className="size-4 text-node-location" />}
                label="Case Isolation"
                description="Secure multi-tenant data"
              />
              <FeaturePill
                icon={<Lock className="size-4 text-node-organization" />}
                label="Audit Trail"
                description="Full activity logging"
              />
            </div>
          </div>

          {/* Bottom: Footer */}
          <div className="flex items-center justify-between text-xs text-slate-400 dark:text-slate-600">
            <span>&copy; {new Date().getFullYear()} OWL Platform</span>
            <span className="font-mono text-[11px] tracking-wider text-slate-400 dark:text-slate-700">
              v2.0
            </span>
          </div>
        </div>
      </div>

      {/* ── Right: Login panel — flush top-to-bottom ── */}
      <div className="relative flex w-full flex-col border-l border-slate-200 dark:border-slate-800/60 bg-card lg:w-[480px] xl:w-[520px]">
        {/* Subtle top accent line */}
        <div className="absolute left-0 right-0 top-0 h-px bg-gradient-to-r from-transparent via-amber-500/40 to-transparent" />

        <div className="flex flex-1 flex-col justify-center px-10 py-12 sm:px-14 xl:px-16">
          {/* Mobile logo — only visible on small screens */}
          <div className="mb-10 flex items-center gap-3 lg:hidden">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-amber-500/10 ring-1 ring-amber-500/20">
              <span className="text-base font-bold tracking-tight text-amber-500">
                O
              </span>
            </div>
            <span className="text-base font-semibold tracking-tight text-slate-900 dark:text-slate-50">
              OWL
            </span>
          </div>

          {/* Header */}
          <div className="mb-8 space-y-2">
            <h2 className="text-2xl font-semibold tracking-tight text-foreground">
              Welcome back
            </h2>
            <p className="text-sm text-muted-foreground">
              Sign in to your account to continue
            </p>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-5">
            <div className="space-y-1.5">
              <label
                htmlFor="username"
                className="block text-xs font-medium text-muted-foreground"
              >
                Username
              </label>
              <Input
                id="username"
                type="text"
                placeholder="Enter your username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                disabled={loading}
                className="h-10"
              />
            </div>

            <div className="space-y-1.5">
              <label
                htmlFor="password"
                className="block text-xs font-medium text-muted-foreground"
              >
                Password
              </label>
              <div className="relative">
                <Input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  placeholder="Enter your password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                  disabled={loading}
                  className="h-10 pr-10"
                />
                <button
                  type="button"
                  tabIndex={-1}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground transition-colors hover:text-foreground"
                  onClick={() => setShowPassword((v) => !v)}
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
              <div className="rounded-md border border-red-200 dark:border-red-500/20 bg-red-50 dark:bg-red-500/10 px-3 py-2 text-xs text-red-600 dark:text-red-400">
                {error}
              </div>
            )}

            <Button
              type="submit"
              variant="primary"
              size="lg"
              className="h-10 w-full"
              disabled={loading || !username || !password}
            >
              {loading ? (
                <LoadingSpinner size="sm" />
              ) : (
                "Sign In"
              )}
            </Button>
          </form>

          {/* Security note */}
          <div className="mt-10 flex items-start gap-2 rounded-md border border-slate-200 dark:border-slate-800/60 bg-slate-50 dark:bg-slate-900/40 px-3.5 py-3">
            <Shield className="mt-0.5 size-3.5 shrink-0 text-slate-400 dark:text-slate-500" />
            <p className="text-[11px] leading-relaxed text-slate-400 dark:text-slate-500">
              This is a secured system. All access attempts are logged and
              monitored. Unauthorized access is prohibited.
            </p>
          </div>
        </div>

        {/* Panel footer */}
        <div className="border-t border-slate-200 dark:border-slate-800/60 px-10 py-4 sm:px-14 xl:px-16">
          <p className="text-center text-[11px] text-slate-400 dark:text-slate-600">
            Protected by enterprise-grade encryption
          </p>
        </div>
      </div>
    </div>
  )
}

/* ── Sub-components ── */

function FeaturePill({
  icon,
  label,
  description,
}: {
  icon: React.ReactNode
  label: string
  description: string
}) {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-slate-200 dark:border-slate-800/60 bg-slate-50/50 dark:bg-slate-900/50 px-3.5 py-3">
      <div className="mt-0.5 shrink-0">{icon}</div>
      <div className="min-w-0">
        <div className="text-sm font-medium text-slate-700 dark:text-slate-200">{label}</div>
        <div className="text-[11px] text-slate-400 dark:text-slate-500">{description}</div>
      </div>
    </div>
  )
}
