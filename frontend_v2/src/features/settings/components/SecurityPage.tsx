import { ScrollArea } from "@/components/ui/scroll-area"
import { ChangePasswordCard } from "./ChangePasswordCard"
import { SettingsNav } from "./SettingsNav"
import { TwoStepCard } from "./TwoStepCard"

export function SecurityPage() {
  return (
    <ScrollArea className="h-full bg-background">
      <div className="mx-auto max-w-2xl space-y-6 p-6">
        <div>
          <h1 className="font-display text-lg font-semibold">Settings</h1>
          <p className="text-xs text-muted-foreground">How you sign in</p>
        </div>
        <SettingsNav />
        <ChangePasswordCard />
        <TwoStepCard />
      </div>
    </ScrollArea>
  )
}
