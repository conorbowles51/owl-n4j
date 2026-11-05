import { useState } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { authAPI } from "@/features/auth/api"
import type { TwoStepStart } from "@/features/auth/auth.types"
import { QrCode } from "./QrCode"

type Change = "codes" | "off"

function RecoveryCodes({ codes, onDone }: { codes: string[]; onDone: () => void }) {
  const text = codes.join("\n") + "\n"
  return (
    <div className="space-y-3">
      <p className="text-xs font-medium">
        Save these recovery codes now. They are shown this once. Each signs you in once if you lose your device.
      </p>
      <pre aria-label="Recovery codes" className="select-all rounded-md border border-border bg-muted/40 p-3 text-xs leading-6">
        {text}
      </pre>
      <div className="flex gap-2">
        <Button asChild variant="outline" size="sm">
          <a href={`data:text/plain;charset=utf-8,${encodeURIComponent(text)}`} download="loupe-recovery-codes.txt">
            Download
          </a>
        </Button>
        <Button variant="primary" size="sm" onClick={onDone}>
          I have saved them
        </Button>
      </div>
    </div>
  )
}

export function TwoStepCard() {
  const queryClient = useQueryClient()
  const { data: status, isLoading, error: loadError } = useQuery({
    queryKey: ["two-step"],
    queryFn: () => authAPI.twoStepStatus(),
  })
  const [password, setPassword] = useState("")
  const [code, setCode] = useState("")
  const [started, setStarted] = useState<TwoStepStart | null>(null)
  const [newCodes, setNewCodes] = useState<string[] | null>(null)
  const [change, setChange] = useState<Change | null>(null)
  const [enrolling, setEnrolling] = useState(false)
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)

  const attempt = async (work: () => Promise<void>) => {
    setError("")
    setBusy(true)
    try {
      await work()
    } catch (err) {
      setError(err instanceof Error ? err.message : "That did not work. Try again.")
    } finally {
      setBusy(false)
    }
  }

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["two-step"] })

  const clear = () => {
    setPassword("")
    setCode("")
    setError("")
  }

  const start = () =>
    attempt(async () => {
      setStarted(await authAPI.twoStepStart(password))
      setPassword("")
    })

  const confirm = () =>
    attempt(async () => {
      const answer = await authAPI.twoStepConfirm(code)
      setStarted(null)
      setEnrolling(false)
      setCode("")
      setNewCodes(answer.recovery_codes)
    })

  const applyChange = () =>
    attempt(async () => {
      if (change === "codes") {
        const answer = await authAPI.twoStepNewRecoveryCodes(password, code)
        setNewCodes(answer.recovery_codes)
      } else {
        await authAPI.twoStepTurnOff(password, code)
        await refresh()
      }
      setChange(null)
      clear()
    })

  const errorLine = error && (
    <p role="alert" className="text-xs text-destructive">
      {error}
    </p>
  )
  const passwordField = (
    <Input
      type="password"
      aria-label="Your password"
      placeholder="Your password"
      autoComplete="current-password"
      value={password}
      onChange={(event) => setPassword(event.target.value)}
    />
  )
  const codeField = (
    <Input
      aria-label="Code from your authenticator app"
      placeholder={status?.enrolled ? "6-digit code, or a recovery code" : "6-digit code"}
      autoComplete="one-time-code"
      value={code}
      onChange={(event) => setCode(event.target.value)}
    />
  )

  const body = () => {
    if (newCodes) {
      return (
        <RecoveryCodes
          codes={newCodes}
          onDone={() => {
            setNewCodes(null)
            void refresh()
          }}
        />
      )
    }
    if (isLoading) return <p className="text-xs text-muted-foreground">Reading your sign-in settings</p>
    if (!status) {
      return (
        <p role="alert" className="text-xs text-destructive">
          {loadError instanceof Error ? loadError.message : "Your sign-in settings could not be read."}
        </p>
      )
    }
    if (status.enrolled) {
      return (
        <div className="space-y-3">
          <p className="text-xs text-muted-foreground">
            You enter a code from your authenticator app after your password. Recovery codes left:{" "}
            <span className="font-medium text-foreground">{status.recovery_codes_left}</span>
          </p>
          {change ? (
            <div className="space-y-3">
              {passwordField}
              {codeField}
              {errorLine}
              <div className="flex gap-2">
                <Button variant="primary" size="sm" onClick={applyChange} disabled={busy || !password || !code.trim()}>
                  {change === "codes" ? "Make new recovery codes" : "Turn off two-step sign-in"}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setChange(null)
                    clear()
                  }}
                >
                  Cancel
                </Button>
              </div>
            </div>
          ) : (
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => setChange("codes")}>
                New recovery codes
              </Button>
              {!status.required && (
                <Button variant="outline" size="sm" onClick={() => setChange("off")}>
                  Turn off
                </Button>
              )}
            </div>
          )}
        </div>
      )
    }
    if (status.unavailable_reason) {
      return <p className="text-xs text-muted-foreground">{status.unavailable_reason}</p>
    }
    if (started) {
      return (
        <div className="space-y-3">
          <p className="text-xs text-muted-foreground">
            Scan this with an authenticator app, then enter the code it shows.
          </p>
          <QrCode rows={started.qr} label="QR code for your authenticator app" />
          <p className="text-xs text-muted-foreground">
            Cannot scan? Enter this key in the app:{" "}
            <code className="select-all break-all rounded bg-muted px-1 py-0.5 text-foreground">{started.secret}</code>
          </p>
          {codeField}
          {errorLine}
          <Button variant="primary" size="sm" onClick={confirm} disabled={busy || !code.trim()}>
            Turn on
          </Button>
        </div>
      )
    }
    if (enrolling) {
      return (
        <div className="space-y-3">
          <p className="text-xs text-muted-foreground">Enter your password to start.</p>
          {passwordField}
          {errorLine}
          <Button variant="primary" size="sm" onClick={start} disabled={busy || !password}>
            Continue
          </Button>
        </div>
      )
    }
    return (
      <div className="space-y-3">
        <p className="text-xs text-muted-foreground">
          {status.required
            ? "Administrators must use two-step sign-in on this server. Turn it on to use the administrator screens."
            : "Ask for a code from an authenticator app after your password, so a stolen password alone cannot sign in."}
        </p>
        <Button variant="primary" size="sm" onClick={() => setEnrolling(true)}>
          Set up two-step sign-in
        </Button>
      </div>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm">
          Two-step sign-in
          {status?.enrolled && <Badge variant="outline">On</Badge>}
        </CardTitle>
      </CardHeader>
      <CardContent>{body()}</CardContent>
    </Card>
  )
}
