import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { authAPI } from "@/features/auth/api"

export function ChangePasswordCard() {
  const [current, setCurrent] = useState("")
  const [next, setNext] = useState("")
  const [repeat, setRepeat] = useState("")
  const [error, setError] = useState("")
  const [done, setDone] = useState(false)
  const [saving, setSaving] = useState(false)

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    setDone(false)
    if (next !== repeat) {
      setError("The two new passwords are different.")
      return
    }
    setError("")
    setSaving(true)
    try {
      await authAPI.changePassword(current, next)
      setCurrent("")
      setNext("")
      setRepeat("")
      setDone(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : "The password could not be changed.")
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Change password</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="space-y-3">
          <p className="text-xs text-muted-foreground">
            You stay signed in here. Any other device signed in to this account is signed out.
          </p>
          <Input
            type="password"
            aria-label="Current password"
            placeholder="Current password"
            autoComplete="current-password"
            value={current}
            onChange={(event) => setCurrent(event.target.value)}
          />
          <Input
            type="password"
            aria-label="New password"
            placeholder="New password (at least 12 characters)"
            autoComplete="new-password"
            value={next}
            onChange={(event) => setNext(event.target.value)}
          />
          <Input
            type="password"
            aria-label="New password again"
            placeholder="New password again"
            autoComplete="new-password"
            value={repeat}
            onChange={(event) => setRepeat(event.target.value)}
          />
          {error && (
            <p role="alert" className="text-xs text-destructive">
              {error}
            </p>
          )}
          {done && (
            <p role="status" className="text-xs text-emerald-600 dark:text-emerald-400">
              Password changed.
            </p>
          )}
          <Button type="submit" variant="primary" size="sm" disabled={saving || !current || !next || !repeat}>
            {saving ? "Changing" : "Change password"}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}
