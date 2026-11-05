import { useEffect, useState } from "react"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { register } from "@/lib/keymap"
import { keyLabel } from "./key-label"
import { useBindings } from "./use-bindings"

/** The `?` overlay (07 4.9): the keys for the current screen, generated from the registry. */
export function KeymapOverlay({ open: controlled, onOpenChange }: { open?: boolean; onOpenChange?: (open: boolean) => void }) {
  const [own, setOwn] = useState(false)
  const open = controlled ?? own
  const setOpen = onOpenChange ?? setOwn
  const bindings = useBindings()
  useEffect(() => register("Keys", [{ key: "?", label: "Show keys", run: () => setOpen(true), hidden: true }]), [setOpen])
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Keys on this screen</DialogTitle>
          <DialogDescription>Every key also has a button on the screen. Keys do nothing while you type in a box, except Esc.</DialogDescription>
        </DialogHeader>
        {bindings.length === 0 ? (
          <p className="text-sm">This screen has no keys of its own.</p>
        ) : (
          <table className="w-full text-sm">
            <caption className="sr-only">Keys and what they do</caption>
            <thead>
              <tr className="text-left text-muted-foreground">
                <th scope="col" className="py-1 pr-4 font-medium">Key</th>
                <th scope="col" className="py-1 font-medium">What it does here</th>
              </tr>
            </thead>
            <tbody>
              {bindings.map((b) => (
                <tr key={b.key} className="border-t">
                  <td className="py-1 pr-4"><kbd className="rounded border bg-muted px-1.5 py-0.5 font-mono text-xs">{keyLabel(b.key)}</kbd></td>
                  <td className="py-1">{b.label}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </DialogContent>
    </Dialog>
  )
}
