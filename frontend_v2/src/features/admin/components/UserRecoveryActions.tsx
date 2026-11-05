import { useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import type { User } from "@/features/auth/auth.types"
import { isSuperAdminUser } from "@/features/auth/auth.types"
import { fetchAPI } from "@/lib/api-client"

interface EnrolledPerson {
  recovery_codes_left: number
}

/** The server decides; this only hides what it would refuse. Never oneself, and only a super admin for an admin. */
function mayRecover(user: User, currentUser: User | null) {
  const role = user.global_role ?? user.role
  const self = (user.email ?? user.username) === (currentUser?.email ?? currentUser?.username)
  return !self && (isSuperAdminUser(currentUser) || (role !== "admin" && role !== "super_admin"))
}

export function UserRecoveryActions({
  user,
  enrolled,
  currentUser,
}: {
  user: User
  enrolled: EnrolledPerson | undefined
  currentUser: User | null
}) {
  const queryClient = useQueryClient()
  const [issued, setIssued] = useState<{ code: string; expires_at: string } | null>(null)
  const [confirming, setConfirming] = useState<"reset" | "remove" | null>(null)
  const path = `/api/users/${encodeURIComponent(user.id ?? "")}`

  const issue = useMutation({
    mutationFn: () => fetchAPI<{ code: string; expires_at: string }>(`${path}/reset-code`, { method: "POST" }),
    onSuccess: (answer) => {
      setConfirming(null)
      setIssued(answer)
    },
  })
  const remove = useMutation({
    mutationFn: () => fetchAPI<void>(`${path}/two-step/remove`, { method: "POST" }),
    onSuccess: () => {
      setConfirming(null)
      void queryClient.invalidateQueries({ queryKey: ["users", "two-step"] })
    },
  })
  const failure = issue.error ?? remove.error

  return (
    <div className="flex items-center gap-2">
      {enrolled ? (
        <Badge variant="outline" title={`${enrolled.recovery_codes_left} recovery codes left`}>
          Two-step on
        </Badge>
      ) : (
        <span className="text-xs text-muted-foreground">No two-step</span>
      )}
      {mayRecover(user, currentUser) && user.is_active !== false && (
        <>
          <Button variant="outline" size="sm" onClick={() => setConfirming("reset")}>
            Reset code
          </Button>
          {enrolled && (
            <Button variant="outline" size="sm" onClick={() => setConfirming("remove")}>
              Remove two-step
            </Button>
          )}
        </>
      )}

      <Dialog
        open={confirming !== null}
        onOpenChange={(open) => {
          if (!open) setConfirming(null)
        }}
      >
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle className="text-sm">
              {confirming === "remove" ? "Remove two-step sign-in" : "Issue a reset code"}
            </DialogTitle>
          </DialogHeader>
          <p className="text-xs text-muted-foreground">
            {confirming === "remove"
              ? `${user.name} will sign in with a password alone until they set it up again. Use this only for a person you have checked, who lost their device and recovery codes.`
              : `Check it is really ${user.name}. The code lets whoever holds it set a new password for this account, and any earlier code stops working. This is recorded under your name.`}
          </p>
          {failure instanceof Error && (
            <p role="alert" className="text-xs text-destructive">
              {failure.message}
            </p>
          )}
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setConfirming(null)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              disabled={issue.isPending || remove.isPending}
              onClick={() => (confirming === "remove" ? remove.mutate() : issue.mutate())}
            >
              {confirming === "remove" ? "Remove" : "Issue code"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={issued !== null}
        onOpenChange={(open) => {
          if (!open) setIssued(null)
        }}
      >
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle className="text-sm">Reset code for {user.name}</DialogTitle>
          </DialogHeader>
          <p className="text-xs text-muted-foreground">
            Give this to them yourself. It is not shown again, works once, and expires at{" "}
            {issued ? new Date(issued.expires_at).toLocaleTimeString() : ""}. On the sign-in page they choose
            &ldquo;I have a reset code&rdquo;.
          </p>
          <code aria-label="Reset code" className="select-all rounded-md border border-border bg-muted/40 p-3 text-center text-sm">
            {issued?.code}
          </code>
          <DialogFooter>
            <Button variant="primary" size="sm" onClick={() => setIssued(null)}>
              Done
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
