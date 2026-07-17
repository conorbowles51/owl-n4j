import { Moon, Sun, Monitor, Keyboard, Bell, Layout } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { Separator } from "@/components/ui/separator"
import { ScrollArea } from "@/components/ui/scroll-area"
import { useTheme } from "@/lib/theme-provider"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import {
  SETTINGS_SHORTCUTS,
  type ShortcutScope,
} from "@/lib/shortcuts-registry"

const scopeLabels: Record<ShortcutScope, string> = {
  global: "Global",
  "page:graph": "Graph",
  "page:timeline": "Timeline",
  "page:table": "Table",
}

export function SettingsPage() {
  const { theme, setTheme } = useTheme()
  const user = useAuthStore((s) => s.user)

  return (
    <ScrollArea className="h-full bg-background">
      <div className="mx-auto max-w-2xl space-y-6 p-6">
        <div>
          <h1 className="font-display text-lg font-semibold">Settings</h1>
          <p className="text-xs text-muted-foreground">
            Manage your personal preferences
          </p>
        </div>

        {/* Profile */}
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Profile</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium">{user?.name || "—"}</p>
                <p className="text-xs text-muted-foreground">
                  {user?.username || "—"}
                </p>
              </div>
              {user?.role && (
                <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-[10px] font-medium text-amber-500">
                  {user.role}
                </span>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Appearance */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm">
              <Sun className="size-4" />
              Appearance
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium">Theme</p>
                <p className="text-xs text-muted-foreground">
                  Select your preferred color scheme
                </p>
              </div>
              <Select value={theme} onValueChange={(v) => setTheme(v as "dark" | "light" | "system")}>
                <SelectTrigger className="w-32">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="dark">
                    <div className="flex items-center gap-2">
                      <Moon className="size-3" />
                      Dark
                    </div>
                  </SelectItem>
                  <SelectItem value="light">
                    <div className="flex items-center gap-2">
                      <Sun className="size-3" />
                      Light
                    </div>
                  </SelectItem>
                  <SelectItem value="system">
                    <div className="flex items-center gap-2">
                      <Monitor className="size-3" />
                      System
                    </div>
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
          </CardContent>
        </Card>

        {/* Keyboard Shortcuts */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm">
              <Keyboard className="size-4" />
              Keyboard Shortcuts
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-1">
              {SETTINGS_SHORTCUTS.map((shortcut) => (
                <div
                  key={shortcut.id}
                  className="flex items-center justify-between gap-3 py-1"
                >
                  <span className="min-w-0">
                    <span className="block truncate text-xs text-muted-foreground">
                      {shortcut.description}
                    </span>
                    <span className="text-[10px] text-muted-foreground/70">
                      {scopeLabels[shortcut.scope]}
                    </span>
                  </span>
                  <kbd className="shrink-0 whitespace-nowrap rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-[10px]">
                    {shortcut.keys}
                  </kbd>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Notifications */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm">
              <Bell className="size-4" />
              Notifications
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-medium">Processing complete</p>
                <p className="text-[10px] text-muted-foreground">
                  Notify when evidence processing finishes
                </p>
              </div>
              <Switch defaultChecked />
            </div>
            <Separator />
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-medium">Chat responses</p>
                <p className="text-[10px] text-muted-foreground">
                  Sound notification for AI responses
                </p>
              </div>
              <Switch />
            </div>
            <Separator />
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-medium">Error alerts</p>
                <p className="text-[10px] text-muted-foreground">
                  Notify on system errors
                </p>
              </div>
              <Switch defaultChecked />
            </div>
          </CardContent>
        </Card>

        {/* Default Views */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm">
              <Layout className="size-4" />
              Default Views
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-medium">Default case view</p>
                <p className="text-[10px] text-muted-foreground">
                  View shown when opening a case
                </p>
              </div>
              <Select defaultValue="graph">
                <SelectTrigger className="w-32">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="graph">Graph</SelectItem>
                  <SelectItem value="timeline">Timeline</SelectItem>
                  <SelectItem value="map">Map</SelectItem>
                  <SelectItem value="table">Table</SelectItem>
                  <SelectItem value="financial">Financial</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </CardContent>
        </Card>
      </div>
    </ScrollArea>
  )
}
