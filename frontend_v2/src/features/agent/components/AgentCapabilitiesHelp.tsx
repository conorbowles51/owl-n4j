import { useEffect, useState } from "react"
import { HelpCircle } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { agentAPI } from "../api"
import type { AgentCapabilities } from "../types"

/** "What can I ask?": every kind of case material the agent works with, in plain words, from the same registry the
 * agent's coverage check uses. Choosing an example puts it in the question box; nothing is sent. */
export function AgentCapabilitiesHelp({ onPick }: { onPick: (question: string) => void }) {
  const [open, setOpen] = useState(false)
  const [help, setHelp] = useState<AgentCapabilities | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open || help) return
    let live = true
    setError(null)
    agentAPI
      .getCapabilities()
      .then((data) => live && setHelp(data))
      .catch(() => live && setError("The list could not be loaded just now. Close this and open it again to retry."))
    return () => {
      live = false
    }
  }, [open, help])

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button type="button" size="sm" variant="ghost" className="h-8 gap-1 text-xs">
          <HelpCircle className="size-4" />
          What can I ask?
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="max-h-[70vh] w-[28rem] overflow-y-auto p-3">
        <h2 className="text-sm font-semibold">What can I ask?</h2>
        {error && <p className="mt-2 text-sm text-muted-foreground">{error}</p>}
        {!help && !error && <p className="mt-2 text-sm text-muted-foreground">Loading…</p>}
        {help && (
          <>
            <p className="mt-1 text-xs text-muted-foreground">
              {help.note} The agent can work with these {help.total} kinds of case material.
            </p>
            <ul className="mt-3 space-y-3" aria-label="Kinds of case material">
              {help.types.map((type) => (
                <li key={type.id}>
                  <h3 className="text-sm font-medium">{type.label}</h3>
                  <p className="text-xs text-muted-foreground">{type.description}</p>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {type.examples.map((example) => (
                      <button
                        key={example}
                        type="button"
                        className="rounded border border-border px-2 py-0.5 text-left text-xs hover:bg-muted"
                        onClick={() => {
                          onPick(example)
                          setOpen(false)
                        }}
                      >
                        {example}
                      </button>
                    ))}
                  </div>
                </li>
              ))}
            </ul>
          </>
        )}
      </PopoverContent>
    </Popover>
  )
}
