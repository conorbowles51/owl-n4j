import { useEffect, useMemo, useState } from "react"
import {
  AlertTriangle,
  BrainCircuit,
  Check,
  ChevronDown,
  ChevronUp,
  CircleDot,
  Cloud,
  KeyRound,
  Loader2,
  LockKeyhole,
  RefreshCw,
  Save,
  ServerCog,
  ShieldCheck,
  Unplug,
} from "lucide-react"
import { toast } from "sonner"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Separator } from "@/components/ui/separator"
import { cn } from "@/lib/cn"
import { aiSettingsAPI } from "../api"
import type { AIProviderConnection, AISettings } from "../types"
import { SettingsNav } from "./SettingsNav"

function ProviderLogo({ provider }: { provider: string }) {
  if (provider === "openai") {
    return (
      <svg
        aria-hidden="true"
        className="size-5"
        data-testid="provider-logo-openai"
        fill="currentColor"
        focusable="false"
        viewBox="0 0 24 24"
      >
        <path
          fillRule="evenodd"
          d="M9.205 8.658v-2.26c0-.19.072-.333.238-.428l4.543-2.616c.619-.357 1.356-.523 2.117-.523 2.854 0 4.662 2.212 4.662 4.566 0 .167 0 .357-.024.547l-4.71-2.759a.797.797 0 0 0-.856 0l-5.97 3.473Zm10.609 8.8V12.06c0-.333-.143-.57-.429-.737l-5.97-3.473 1.95-1.118a.433.433 0 0 1 .476 0l4.543 2.617c1.309.76 2.189 2.378 2.189 3.948 0 1.808-1.07 3.473-2.76 4.163ZM7.802 12.703l-1.95-1.142c-.167-.095-.239-.238-.239-.428V5.899c0-2.545 1.95-4.472 4.591-4.472 1 0 1.927.333 2.712.928L8.23 5.067c-.285.166-.428.404-.428.737v6.898ZM12 15.128l-2.795-1.57v-3.33L12 8.658l2.795 1.57v3.33L12 15.128Zm1.796 7.23c-1 0-1.927-.332-2.712-.927l4.686-2.712c.285-.166.428-.404.428-.737v-6.898l1.974 1.142c.167.095.238.238.238.428v5.233c0 2.545-1.974 4.472-4.614 4.472Zm-5.637-5.303-4.544-2.617c-1.308-.761-2.188-2.378-2.188-3.948A4.482 4.482 0 0 1 4.21 6.327v5.423c0 .333.143.571.428.738l5.947 3.449-1.95 1.118a.432.432 0 0 1-.476 0Zm-.262 3.9c-2.688 0-4.662-2.021-4.662-4.519 0-.19.024-.38.047-.57l4.686 2.71c.286.167.571.167.856 0l5.97-3.448v2.26c0 .19-.07.333-.237.428l-4.543 2.616c-.619.357-1.356.523-2.117.523Zm5.899 2.83a5.947 5.947 0 0 0 5.827-4.756C22.287 18.339 24 15.84 24 13.296c0-1.665-.713-3.282-1.998-4.448.119-.5.19-.999.19-1.498 0-3.401-2.759-5.947-5.946-5.947-.642 0-1.26.095-1.88.31A5.962 5.962 0 0 0 10.205 0a5.947 5.947 0 0 0-5.827 4.757C1.713 5.447 0 7.945 0 10.49c0 1.666.713 3.283 1.998 4.448-.119.5-.19 1-.19 1.499 0 3.401 2.759 5.946 5.946 5.946.642 0 1.26-.095 1.88-.309a5.96 5.96 0 0 0 4.162 1.713Z"
        />
      </svg>
    )
  }

  if (provider === "anthropic") {
    return (
      <svg
        aria-hidden="true"
        className="size-5"
        data-testid="provider-logo-anthropic"
        fill="currentColor"
        focusable="false"
        viewBox="0 0 24 24"
      >
        <path d="M13.827 3.52h3.603L24 20h-3.603l-6.57-16.48Zm-7.258 0h3.767L16.906 20h-3.674l-1.343-3.461H5.017L3.673 20H0L6.57 3.522Zm4.132 9.959L8.453 7.687 6.205 13.48H10.7Z" />
      </svg>
    )
  }

  if (provider === "gemini") {
    const geminiPath =
      "M20.616 10.835a14.147 14.147 0 0 1-4.45-3.001 14.111 14.111 0 0 1-3.678-6.452.503.503 0 0 0-.975 0 14.134 14.134 0 0 1-3.679 6.452 14.155 14.155 0 0 1-4.45 3.001c-.65.28-1.318.505-2.002.678a.502.502 0 0 0 0 .975c.684.172 1.35.397 2.002.677a14.147 14.147 0 0 1 4.45 3.001 14.112 14.112 0 0 1 3.679 6.453.502.502 0 0 0 .975 0c.172-.685.397-1.351.677-2.003a14.145 14.145 0 0 1 3.001-4.45 14.113 14.113 0 0 1 6.453-3.678.503.503 0 0 0 0-.975 13.245 13.245 0 0 1-2.003-.678Z"

    return (
      <svg
        aria-hidden="true"
        className="size-5"
        data-testid="provider-logo-gemini"
        focusable="false"
        viewBox="0 0 24 24"
      >
        <path d={geminiPath} fill="#3186ff" />
        <path d={geminiPath} fill="url(#gemini-green)" />
        <path d={geminiPath} fill="url(#gemini-red)" />
        <path d={geminiPath} fill="url(#gemini-yellow)" />
        <defs>
          <linearGradient id="gemini-green" x1="7" x2="11" y1="15.5" y2="12" gradientUnits="userSpaceOnUse">
            <stop stopColor="#08b962" />
            <stop offset="1" stopColor="#08b962" stopOpacity="0" />
          </linearGradient>
          <linearGradient id="gemini-red" x1="8" x2="11.5" y1="5.5" y2="11" gradientUnits="userSpaceOnUse">
            <stop stopColor="#f94543" />
            <stop offset="1" stopColor="#f94543" stopOpacity="0" />
          </linearGradient>
          <linearGradient id="gemini-yellow" x1="3.5" x2="17.5" y1="13.5" y2="12" gradientUnits="userSpaceOnUse">
            <stop stopColor="#fabc12" />
            <stop offset=".46" stopColor="#fabc12" stopOpacity="0" />
          </linearGradient>
        </defs>
      </svg>
    )
  }

  return <BrainCircuit aria-hidden="true" className="size-5" />
}

function statusLabel(provider: AIProviderConnection) {
  if (provider.status === "connected") return "Connected"
  if (provider.status === "unavailable") return "Connection issue"
  if (provider.status === "invalid") return "Key rejected"
  return "API key needed"
}

function providerDisplay(provider: string) {
  if (provider === "openai") return "OpenAI"
  if (provider === "gemini") return "Google Gemini"
  if (provider === "tesseract") return "Local Tesseract"
  if (provider === "local") return "Local service"
  return provider.charAt(0).toUpperCase() + provider.slice(1)
}

export function AISettingsPage() {
  const [settings, setSettings] = useState<AISettings | null>(null)
  const [draft, setDraft] = useState<AISettings["routing"]>({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [advanced, setAdvanced] = useState(false)
  const [credentialProvider, setCredentialProvider] = useState<AIProviderConnection | null>(null)
  const [credentialValue, setCredentialValue] = useState("")
  const [credentialSaving, setCredentialSaving] = useState(false)
  const [testingProvider, setTestingProvider] = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    try {
      const result = await aiSettingsAPI.get()
      setSettings(result)
      setDraft(result.routing)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to load AI settings")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const connectedCount = settings?.providers.filter((provider) => provider.configured).length ?? 0
  const isDirty = settings ? JSON.stringify(draft) !== JSON.stringify(settings.routing) : false
  const selectedProvider = useMemo(() => {
    const providers = new Set(Object.values(draft).map((entry) => entry.provider))
    return providers.size === 1 ? Array.from(providers)[0] : "mixed"
  }, [draft])
  const groups = useMemo(() => {
    if (!settings) return []
    const grouped = new Map<string, string[]>()
    Object.keys(settings.workloads).forEach((workload) => {
      const group = settings.workloads[workload].group
      grouped.set(group, [...(grouped.get(group) ?? []), workload])
    })
    return Array.from(grouped.entries())
  }, [settings])

  const applyProvider = (provider: string) => {
    if (!settings || provider === "mixed") return
    const profile = settings.recommended_profiles[provider]
    if (profile) setDraft(profile)
  }

  const savePolicy = async () => {
    if (!settings || !isDirty) return
    setSaving(true)
    try {
      const result = await aiSettingsAPI.updatePolicy(settings.policy_revision, draft)
      setSettings(result)
      setDraft(result.routing)
      toast.success("AI routing saved")
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to save AI routing")
    } finally {
      setSaving(false)
    }
  }

  const connectProvider = async () => {
    if (!credentialProvider || !credentialValue.trim()) return
    setCredentialSaving(true)
    try {
      await aiSettingsAPI.saveCredential(
        credentialProvider.id,
        credentialValue.trim(),
        credentialProvider.revision
      )
      setCredentialValue("")
      setCredentialProvider(null)
      await load()
      toast.success(`${credentialProvider.display_name} connected`)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "The provider could not be connected")
    } finally {
      setCredentialSaving(false)
    }
  }

  const testProvider = async (provider: AIProviderConnection) => {
    setTestingProvider(provider.id)
    try {
      await aiSettingsAPI.testCredential(provider.id)
      toast.success(`${provider.display_name} connection verified`)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Connection test failed")
    } finally {
      setTestingProvider(null)
    }
  }

  const disconnectProvider = async (provider: AIProviderConnection) => {
    if (provider.in_use_by.length) {
      toast.error("Move active workloads to another provider before disconnecting")
      return
    }
    try {
      await aiSettingsAPI.disconnectCredential(provider.id, provider.revision)
      await load()
      toast.success(`${provider.display_name} disconnected`)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Provider could not be disconnected")
    }
  }

  return (
    <ScrollArea className="h-full bg-background">
      <div className="mx-auto max-w-5xl space-y-6 p-6 pb-16">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <div className="mb-2 flex items-center gap-2">
              <Badge variant="outline" className="gap-1 text-[10px] uppercase tracking-[0.13em]">
                <LockKeyhole className="size-3" /> Instance-wide
              </Badge>
            </div>
            <h1 className="font-display text-xl font-semibold tracking-tight">AI settings</h1>
            <p className="mt-1 max-w-2xl text-xs leading-relaxed text-muted-foreground">
              Connect providers once, then control the models Loupe uses for chat, agents, and evidence ingestion.
            </p>
          </div>
          <Button onClick={savePolicy} disabled={!isDirty || saving || !settings?.permissions.can_edit_routing}>
            {saving ? <Loader2 className="size-3.5 animate-spin" /> : <Save className="size-3.5" />}
            Save routing
          </Button>
        </div>

        <SettingsNav />

        {loading && !settings ? (
          <div className="flex min-h-72 items-center justify-center rounded-xl border border-dashed border-border">
            <div className="text-center text-xs text-muted-foreground">
              <Loader2 className="mx-auto mb-2 size-5 animate-spin" /> Loading AI control room…
            </div>
          </div>
        ) : null}

        {settings ? (
          <>
            {connectedCount === 0 ? (
              <div className="flex flex-col gap-3 rounded-xl border border-brand-400/30 bg-brand-50/70 p-4 dark:bg-brand-400/[0.06] sm:flex-row sm:items-center sm:justify-between">
                <div className="flex items-start gap-3">
                  <div className="rounded-lg bg-brand-500 p-2 text-white"><KeyRound className="size-4" /></div>
                  <div>
                    <p className="text-xs font-semibold">Connect your first AI provider</p>
                    <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">Start with OpenAI for the broadest ingestion support, or connect Anthropic or Gemini for generative analysis.</p>
                  </div>
                </div>
                <Button size="sm" onClick={() => setCredentialProvider(settings.providers[0])} disabled={!settings.permissions.can_manage_credentials}>Connect OpenAI</Button>
              </div>
            ) : null}

            <div className="grid gap-3 sm:grid-cols-3">
              <div className="rounded-xl border border-border/70 bg-card p-4 shadow-sm">
                <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Connections</p>
                <p className="mt-2 font-display text-2xl font-semibold tabular-nums">{connectedCount}<span className="text-sm text-muted-foreground"> / 3</span></p>
                <p className="mt-1 text-[11px] text-muted-foreground">Cloud providers ready</p>
              </div>
              <div className="rounded-xl border border-border/70 bg-card p-4 shadow-sm">
                <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Default route</p>
                <p className="mt-2 truncate font-display text-base font-semibold">{providerDisplay(selectedProvider)}</p>
                <p className="mt-1 text-[11px] text-muted-foreground">Across {Object.keys(settings.workloads).length} AI workloads</p>
              </div>
              <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/[0.045] p-4 shadow-sm">
                <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-emerald-700 dark:text-emerald-300">Credential security</p>
                <p className="mt-2 flex items-center gap-2 font-display text-base font-semibold"><ShieldCheck className="size-4 text-emerald-600" /> Encrypted at rest</p>
                <p className="mt-1 text-[11px] text-muted-foreground">Keys are never shown again after saving</p>
              </div>
            </div>

            <section className="space-y-3" aria-labelledby="provider-connections-heading">
              <div>
                <h2 id="provider-connections-heading" className="font-display text-sm font-semibold">Provider connections</h2>
                <p className="mt-0.5 text-[11px] text-muted-foreground">Credentials are shared by this Loupe deployment.</p>
              </div>
              <div className="grid gap-3 lg:grid-cols-3">
                {settings.providers.map((provider) => (
                  <Card key={provider.id} className={cn("overflow-hidden", provider.configured && "border-brand-400/35")}>
                    <div className={cn("h-1", provider.configured ? "bg-brand-500" : "bg-muted")} />
                    <CardHeader className="pb-3">
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex items-center gap-3">
                          <div className="flex size-9 items-center justify-center rounded-lg border border-border/70 bg-muted/60 text-foreground">
                            <ProviderLogo provider={provider.id} />
                          </div>
                          <div>
                            <CardTitle className="text-sm">{provider.display_name}</CardTitle>
                            <div className={cn("mt-1 flex items-center gap-1.5 text-[10px]", provider.configured ? "text-emerald-600 dark:text-emerald-300" : "text-muted-foreground")}>
                              <CircleDot className="size-3" /> {statusLabel(provider)}
                            </div>
                          </div>
                        </div>
                      </div>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <p className="min-h-10 text-[11px] leading-relaxed text-muted-foreground">{provider.description}</p>
                      {provider.key_last_four ? (
                        <div className="rounded-md border border-border/65 bg-muted/30 px-3 py-2">
                          <div className="flex items-center justify-between gap-2">
                            <span className="font-mono text-[11px] tracking-wider">••••••••{provider.key_last_four}</span>
                            <Badge variant="secondary" className="text-[9px]">{provider.source === "environment" ? "Environment" : "Encrypted"}</Badge>
                          </div>
                        </div>
                      ) : null}
                      {settings.permissions.can_manage_credentials ? (
                        <div className="flex flex-wrap gap-2">
                          <Button
                            size="sm"
                            variant={provider.key_last_four ? "outline" : "primary"}
                            aria-label={`${provider.key_last_four ? "Replace" : "Configure"} ${provider.display_name}`}
                            onClick={() => setCredentialProvider(provider)}
                          >
                            <KeyRound className="size-3.5" /> {provider.key_last_four ? "Replace" : "Configure"}
                          </Button>
                          {provider.key_last_four ? (
                            <>
                              <Button size="sm" variant="ghost" onClick={() => void testProvider(provider)} disabled={testingProvider === provider.id}>
                                {testingProvider === provider.id ? <Loader2 className="size-3.5 animate-spin" /> : <RefreshCw className="size-3.5" />} Test
                              </Button>
                              <Button size="icon" variant="ghost" title={`Disconnect ${provider.display_name}`} onClick={() => void disconnectProvider(provider)} disabled={provider.in_use_by.length > 0}>
                                <Unplug className="size-3.5" />
                              </Button>
                            </>
                          ) : null}
                        </div>
                      ) : null}
                    </CardContent>
                  </Card>
                ))}
              </div>
            </section>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-sm"><BrainCircuit className="size-4" /> Default generative provider</CardTitle>
                <p className="text-[11px] text-muted-foreground">Choosing a provider loads Loupe’s recommended model profile. Review and save to apply it.</p>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <p className="text-xs font-medium">Provider profile</p>
                    <p className="text-[10px] text-muted-foreground">Only connected providers can be selected.</p>
                  </div>
                  <Select value={selectedProvider} onValueChange={applyProvider} disabled={!settings.permissions.can_edit_routing}>
                    <SelectTrigger className="w-full sm:w-60" aria-label="Default AI provider"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {settings.providers.map((provider) => (
                        <SelectItem key={provider.id} value={provider.id} disabled={!provider.configured}>
                          {provider.display_name}{provider.configured ? "" : " · Add key first"}
                        </SelectItem>
                      ))}
                      {selectedProvider === "mixed" ? <SelectItem value="mixed" disabled>Custom mix</SelectItem> : null}
                    </SelectContent>
                  </Select>
                </div>
                {isDirty ? (
                  <div className="flex items-start gap-2 rounded-md border border-amber-500/25 bg-amber-500/[0.055] p-3 text-[11px] text-amber-800 dark:text-amber-200">
                    <AlertTriangle className="mt-0.5 size-3.5 shrink-0" /> Routing changes are staged. Save routing to make them active.
                  </div>
                ) : null}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-3">
                <button type="button" className="flex w-full items-start justify-between gap-3 text-left" onClick={() => setAdvanced((value) => !value)} aria-expanded={advanced}>
                  <div>
                    <CardTitle className="flex items-center gap-2 text-sm"><ServerCog className="size-4" /> Advanced model routing</CardTitle>
                    <p className="mt-1 text-[11px] text-muted-foreground">Choose a different connected model for an individual Loupe workload.</p>
                  </div>
                  {advanced ? <ChevronUp className="size-4 text-muted-foreground" /> : <ChevronDown className="size-4 text-muted-foreground" />}
                </button>
              </CardHeader>
              {advanced ? (
                <CardContent className="space-y-5">
                  {groups.map(([group, workloads]) => (
                    <section key={group} className="space-y-2">
                      <h3 className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">{group}</h3>
                      {workloads.map((workload) => {
                        const metadata = settings.workloads[workload]
                        const current = draft[workload]
                        const available = settings.models.filter((model) => {
                          if (model.provider_configured === false) return false
                          if (workload === "agent" && model.supports_agent === false) return false
                          if (workload.startsWith("ingestion_") && model.supports_structured_output === false) return false
                          return true
                        })
                        return (
                          <div key={workload} className="flex flex-col gap-3 rounded-lg border border-border/65 p-3 sm:flex-row sm:items-center sm:justify-between">
                            <div className="min-w-0">
                              <p className="text-xs font-medium">{metadata.label}</p>
                              <p className="text-[10px] leading-relaxed text-muted-foreground">{metadata.description}</p>
                            </div>
                            <Select
                              value={current?.model_id ?? ""}
                              disabled={!settings.permissions.can_edit_routing}
                              onValueChange={(modelId) => {
                                const model = settings.models.find((candidate) => candidate.id === modelId)
                                if (!model) return
                                setDraft((existing) => ({ ...existing, [workload]: { provider: model.provider, model_id: model.id } }))
                              }}
                            >
                              <SelectTrigger className="w-full shrink-0 text-xs sm:w-56"><SelectValue /></SelectTrigger>
                              <SelectContent>
                                {available.map((model) => <SelectItem key={model.id} value={model.id}>{model.name} · {providerDisplay(model.provider)}</SelectItem>)}
                              </SelectContent>
                            </Select>
                          </div>
                        )
                      })}
                    </section>
                  ))}
                </CardContent>
              ) : null}
            </Card>

            <section className="space-y-3" aria-labelledby="supporting-services-heading">
              <div>
                <h2 id="supporting-services-heading" className="font-display text-sm font-semibold">Supporting AI services</h2>
                <p className="mt-0.5 text-[11px] text-muted-foreground">These services support ingestion independently of the generative provider above.</p>
              </div>
              <Card>
                <CardContent className="divide-y divide-border/65 p-0">
                  {settings.supporting_services.map((service) => (
                    <div key={service.id} className="flex items-start justify-between gap-4 px-4 py-3.5">
                      <div className="flex min-w-0 items-start gap-3">
                        <div className="mt-0.5 rounded-md border border-border/65 bg-muted/50 p-1.5"><Cloud className="size-3.5" /></div>
                        <div>
                          <p className="text-xs font-medium">{service.label}</p>
                          <p className="mt-0.5 text-[10px] text-muted-foreground">{service.description}</p>
                        </div>
                      </div>
                      <div className="shrink-0 text-right">
                        <p className="text-[10px] font-medium">{providerDisplay(service.provider)}</p>
                        <p className={cn("mt-0.5 flex items-center justify-end gap-1 text-[9px]", service.status === "ready" ? "text-emerald-600" : "text-amber-600")}>
                          {service.status === "ready" ? <Check className="size-3" /> : <AlertTriangle className="size-3" />}
                          {service.status === "ready" ? "Ready" : "Needs key"}
                        </p>
                      </div>
                    </div>
                  ))}
                </CardContent>
              </Card>
            </section>

            {!settings.permissions.can_edit_routing ? (
              <p className="text-[10px] text-muted-foreground">These are deployment-wide settings. An administrator can change model routing.</p>
            ) : null}
          </>
        ) : null}
      </div>

      <Dialog open={Boolean(credentialProvider)} onOpenChange={(open) => {
        if (!open && !credentialSaving) {
          setCredentialValue("")
          setCredentialProvider(null)
        }
      }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{credentialProvider?.key_last_four ? "Replace" : "Connect"} {credentialProvider?.display_name}</DialogTitle>
            <DialogDescription>
              Loupe validates the key before encrypting it. A rejected replacement will not disturb the current connection.
            </DialogDescription>
          </DialogHeader>
          {credentialProvider ? (
            <div className="space-y-2">
              <Label htmlFor="provider-api-key">{credentialProvider.display_name} API key</Label>
              <Input
                id="provider-api-key"
                type="password"
                value={credentialValue}
                onChange={(event) => setCredentialValue(event.target.value)}
                autoComplete="off"
                spellCheck={false}
                placeholder="Paste API key"
                autoFocus
              />
              <p className="text-[10px] leading-relaxed text-muted-foreground">The full key is submitted once and is never returned to this browser.</p>
            </div>
          ) : null}
          <Separator />
          <DialogFooter>
            <Button variant="outline" onClick={() => {
              setCredentialValue("")
              setCredentialProvider(null)
            }} disabled={credentialSaving}>Cancel</Button>
            <Button onClick={() => void connectProvider()} disabled={!credentialValue.trim() || credentialSaving}>
              {credentialSaving ? <Loader2 className="size-3.5 animate-spin" /> : <ShieldCheck className="size-3.5" />}
              Validate and connect
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </ScrollArea>
  )
}
