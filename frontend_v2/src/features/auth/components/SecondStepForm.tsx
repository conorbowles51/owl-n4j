import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { authAPI } from "../api"
import type { SignedIn } from "../auth.types"

/** The code after the password: six digits from the authenticator app, or a recovery code. */
export function SecondStepForm({
  token,
  onSignedIn,
  onCancel,
}: {
  token: string
  onSignedIn: (response: SignedIn) => void
  onCancel: () => void
}) {
  const [code, setCode] = useState("")
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    setError("")
    setLoading(true)
    try {
      onSignedIn(await authAPI.loginSecondStep(token, code))
    } catch (err) {
      setCode("")
      setError(err instanceof Error ? err.message : "Sign-in failed. Please try again.")
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={submit} className="mt-7 space-y-5">
      <div className="space-y-2">
        <label htmlFor="second-step-code" className="block text-[13px] font-semibold text-foreground">
          Code from your authenticator app
        </label>
        <Input
          id="second-step-code"
          value={code}
          onChange={(event) => setCode(event.target.value)}
          autoComplete="one-time-code"
          autoFocus
          disabled={loading}
          aria-invalid={Boolean(error)}
          className="h-11 bg-background/90 shadow-sm dark:bg-background/55"
        />
        <p className="text-xs leading-5 text-muted-foreground">
          Lost your device? Enter one of your recovery codes instead. Each works once.
        </p>
      </div>

      {error && (
        <div
          role="alert"
          className="rounded-md border border-red-200 bg-red-50 px-3.5 py-2.5 text-xs leading-5 text-red-700 dark:border-red-500/20 dark:bg-red-500/10 dark:text-red-300"
        >
          {error}
        </div>
      )}

      <Button type="submit" variant="primary" size="lg" className="h-11 w-full" disabled={loading || !code.trim()}>
        {loading ? (
          <>
            <LoadingSpinner size="sm" />
            Checking
          </>
        ) : (
          "Continue"
        )}
      </Button>
      <button
        type="button"
        className="block w-full text-center text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
        onClick={onCancel}
      >
        Back to sign-in
      </button>
    </form>
  )
}
