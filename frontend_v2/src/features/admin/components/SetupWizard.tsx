import { useState } from "react"
import { Sparkles, Check } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { setupAPI } from "../api"

interface SetupWizardProps {
  onComplete: () => void
}

export function SetupWizard({ onComplete }: SetupWizardProps) {
  const [step, setStep] = useState(0)
  const [email, setEmail] = useState("")
  const [name, setName] = useState("")
  const [password, setPassword] = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState("")

  const handleSubmit = async () => {
    if (password !== confirmPassword) {
      setError("Passwords do not match")
      return
    }
    setIsSubmitting(true)
    setError("")
    try {
      await setupAPI.createInitialUser({ email, name, password })
      setStep(1)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Setup failed")
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="flex h-screen items-center justify-center bg-background">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <div className="mx-auto mb-2 flex size-12 items-center justify-center rounded-full bg-amber-50 dark:bg-amber-500/10">
            {step === 0 ? (
              <Sparkles className="size-6 text-amber-500" />
            ) : (
              <Check className="size-6 text-emerald-500" />
            )}
          </div>
          <CardTitle className="text-lg">
            {step === 0 ? "Welcome to Owl" : "Setup Complete"}
          </CardTitle>
          <p className="text-xs text-muted-foreground">
            {step === 0
              ? "Create your admin account to get started"
              : "Your admin account has been created"}
          </p>
        </CardHeader>
        <CardContent>
          {step === 0 ? (
            <div className="space-y-3">
              <Input
                placeholder="Email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
              <Input
                placeholder="Display name"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
              <Input
                placeholder="Password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <Input
                placeholder="Confirm password"
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
              />
              {error && (
                <p className="text-xs text-red-500">{error}</p>
              )}
              <Button
                variant="primary"
                className="w-full"
                onClick={handleSubmit}
                disabled={
                  !email || !name || !password || !confirmPassword || isSubmitting
                }
              >
                {isSubmitting ? "Creating..." : "Create Admin Account"}
              </Button>
            </div>
          ) : (
            <Button
              variant="primary"
              className="w-full"
              onClick={onComplete}
            >
              Continue to Login
            </Button>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
