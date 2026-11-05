import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { authAPI } from "../api"

/** A new password from the one-time code an administrator gave this person. */
export function ResetWithCodeForm({
  initialEmail,
  onDone,
  onCancel,
}: {
  initialEmail: string
  onDone: (message: string) => void
  onCancel: () => void
}) {
  const [email, setEmail] = useState(initialEmail)
  const [code, setCode] = useState("")
  const [password, setPassword] = useState("")
  const [repeat, setRepeat] = useState("")
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (password !== repeat) {
      setError("The two passwords are different.")
      return
    }
    setError("")
    setLoading(true)
    try {
      await authAPI.resetWithCode(email.trim(), code, password)
      onDone("Password set. Sign in with it.")
    } catch (err) {
      setError(err instanceof Error ? err.message : "The password could not be set.")
    } finally {
      setLoading(false)
    }
  }

  const field = "h-11 bg-background/90 shadow-sm dark:bg-background/55"
  const label = "block text-[13px] font-semibold text-foreground"
  return (
    <form onSubmit={submit} className="mt-7 space-y-4">
      <p className="text-xs leading-5 text-muted-foreground">
        An administrator gives you a reset code. It works once and expires after an hour. This server sends no email.
      </p>
      <div className="space-y-2">
        <label htmlFor="reset-email" className={label}>
          Username
        </label>
        <Input
          id="reset-email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          autoComplete="username"
          disabled={loading}
          className={field}
        />
      </div>
      <div className="space-y-2">
        <label htmlFor="reset-code" className={label}>
          Reset code
        </label>
        <Input
          id="reset-code"
          value={code}
          onChange={(event) => setCode(event.target.value)}
          autoComplete="off"
          disabled={loading}
          className={field}
        />
      </div>
      <div className="space-y-2">
        <label htmlFor="reset-password" className={label}>
          New password
        </label>
        <Input
          id="reset-password"
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          placeholder="At least 12 characters"
          autoComplete="new-password"
          disabled={loading}
          className={field}
        />
      </div>
      <div className="space-y-2">
        <label htmlFor="reset-repeat" className={label}>
          New password again
        </label>
        <Input
          id="reset-repeat"
          type="password"
          value={repeat}
          onChange={(event) => setRepeat(event.target.value)}
          autoComplete="new-password"
          disabled={loading}
          className={field}
        />
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
        disabled={loading || !email.trim() || !code.trim() || !password || !repeat}
      >
        {loading ? (
          <>
            <LoadingSpinner size="sm" />
            Setting password
          </>
        ) : (
          "Set new password"
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
