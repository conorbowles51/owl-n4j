import { useState, useEffect } from "react"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Slider } from "@/components/ui/slider"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import {
  Settings,
  Plus,
  Trash2,
  Info,
  FileText,
  MessageSquare,
  Cpu,
  AlertCircle,
} from "lucide-react"
import { useProfile, useProfiles, useSaveProfile } from "../hooks/use-profiles"
import { llmConfigAPI } from "../api"
import type { ProfileSaveData, SpecialEntityType, LLMModel } from "@/types/evidence.types"
import { toast } from "sonner"

interface ProfileEditorDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  editingProfile?: string
  cloneFrom?: string
  onSaved?: () => void
}

export function ProfileEditorDialog({
  open,
  onOpenChange,
  editingProfile,
  cloneFrom,
  onSaved,
}: ProfileEditorDialogProps) {
  const { data: existingProfile, isLoading: profileLoading } = useProfile(
    editingProfile || cloneFrom || undefined
  )
  useProfiles() // preload profiles list
  const saveMutation = useSaveProfile()

  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [caseType, setCaseType] = useState("")
  const [ingestionSystemContext, setIngestionSystemContext] = useState("")
  const [specialEntityTypes, setSpecialEntityTypes] = useState<SpecialEntityType[]>([])
  const [ingestionTemperature, setIngestionTemperature] = useState(1.0)
  const [chatSystemContext, setChatSystemContext] = useState("")
  const [chatAnalysisGuidance, setChatAnalysisGuidance] = useState("")
  const [chatTemperature, setChatTemperature] = useState(1.0)
  const [llmProvider, setLlmProvider] = useState("openai")
  const [llmModelId, setLlmModelId] = useState("")
  const [availableModels, setAvailableModels] = useState<LLMModel[]>([])
  const [error, setError] = useState<string | null>(null)

  // Load models
  useEffect(() => {
    if (open) {
      llmConfigAPI.getModels().then((res) => setAvailableModels(res.models ?? []))
        .catch(() => {})
    }
  }, [open])

  // Populate from existing profile
  useEffect(() => {
    if (!existingProfile) return
    if (editingProfile) setName(existingProfile.name)
    setDescription(existingProfile.description ?? "")
    setCaseType(existingProfile.case_type ?? "")
    setIngestionSystemContext(existingProfile.ingestion?.system_context ?? "")
    setSpecialEntityTypes(existingProfile.ingestion?.special_entity_types ?? [])
    setIngestionTemperature(existingProfile.ingestion?.temperature ?? 1.0)
    setChatSystemContext(existingProfile.chat?.system_context ?? "")
    setChatAnalysisGuidance(existingProfile.chat?.analysis_guidance ?? "")
    setChatTemperature(existingProfile.chat?.temperature ?? 1.0)
    setLlmProvider(existingProfile.llm_config?.provider ?? "openai")
    setLlmModelId(existingProfile.llm_config?.model_id ?? "")
  }, [existingProfile, editingProfile])

  // Reset on close
  useEffect(() => {
    if (!open) {
      setName("")
      setDescription("")
      setCaseType("")
      setIngestionSystemContext("")
      setSpecialEntityTypes([])
      setIngestionTemperature(1.0)
      setChatSystemContext("")
      setChatAnalysisGuidance("")
      setChatTemperature(1.0)
      setLlmProvider("openai")
      setLlmModelId("")
      setError(null)
    }
  }, [open])

  const handleSave = () => {
    if (!name.trim()) {
      setError("Profile name is required")
      return
    }
    if (!description.trim()) {
      setError("Description is required")
      return
    }
    setError(null)

    const data: ProfileSaveData = {
      name: name.trim(),
      description: description.trim(),
      case_type: caseType.trim() || null,
      ingestion_system_context: ingestionSystemContext.trim() || null,
      special_entity_types: specialEntityTypes.filter((e) => e.name?.trim()),
      ingestion_temperature: ingestionTemperature,
      llm_provider: llmProvider,
      llm_model_id: llmModelId,
      chat_system_context: chatSystemContext.trim() || null,
      chat_analysis_guidance: chatAnalysisGuidance.trim() || null,
      chat_temperature: chatTemperature,
    }

    saveMutation.mutate(data, {
      onSuccess: () => {
        toast.success("Profile saved")
        onSaved?.()
        onOpenChange(false)
      },
      onError: (err) => {
        setError(err.message)
      },
    })
  }

  const filteredModels = availableModels.filter((m) => m.provider === llmProvider)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[85vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Settings className="size-4" />
            {editingProfile ? "Edit Profile" : cloneFrom ? "Clone Profile" : "Create Profile"}
          </DialogTitle>
        </DialogHeader>

        {profileLoading ? (
          <div className="flex justify-center py-12">
            <LoadingSpinner />
          </div>
        ) : (
          <div className="flex-1 overflow-auto">
            {error && (
              <div className="mb-4 flex items-start gap-2 rounded-md bg-red-50 dark:bg-red-500/10 p-3">
                <AlertCircle className="mt-0.5 size-4 text-red-600 dark:text-red-400" />
                <p className="text-xs text-red-600 dark:text-red-400">{error}</p>
              </div>
            )}

            <Tabs defaultValue="basic" className="w-full">
              <TabsList variant="line" className="w-full mb-4">
                <TabsTrigger value="basic">
                  <Info className="size-3" />
                  Basic
                </TabsTrigger>
                <TabsTrigger value="ingestion">
                  <FileText className="size-3" />
                  Ingestion
                </TabsTrigger>
                <TabsTrigger value="chat">
                  <MessageSquare className="size-3" />
                  Chat
                </TabsTrigger>
                <TabsTrigger value="llm">
                  <Cpu className="size-3" />
                  LLM
                </TabsTrigger>
              </TabsList>

              <TabsContent value="basic" className="space-y-4">
                <div>
                  <label className="mb-1 block text-xs font-medium">Profile Name *</label>
                  <Input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="e.g. fraud-investigation"
                    disabled={!!editingProfile}
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium">Description *</label>
                  <Textarea
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="Brief description of this profile"
                    className="min-h-[80px]"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium">Case Type</label>
                  <Input
                    value={caseType}
                    onChange={(e) => setCaseType(e.target.value)}
                    placeholder="e.g. Fraud Investigation"
                  />
                </div>
              </TabsContent>

              <TabsContent value="ingestion" className="space-y-4">
                <div>
                  <label className="mb-1 block text-xs font-medium">System Context</label>
                  <Textarea
                    value={ingestionSystemContext}
                    onChange={(e) => setIngestionSystemContext(e.target.value)}
                    placeholder="System prompt for entity extraction..."
                    className="min-h-[120px] font-mono text-xs"
                  />
                </div>

                <div>
                  <div className="mb-2 flex items-center justify-between">
                    <label className="text-xs font-medium">Special Entity Types</label>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() =>
                        setSpecialEntityTypes([{ name: "", description: "" }, ...specialEntityTypes])
                      }
                      className="h-6 text-xs"
                    >
                      <Plus className="size-3" />
                      Add
                    </Button>
                  </div>
                  {specialEntityTypes.map((entity, i) => (
                    <div key={i} className="mb-2 flex items-start gap-2">
                      <Input
                        value={entity.name}
                        onChange={(e) => {
                          const updated = [...specialEntityTypes]
                          updated[i] = { ...updated[i], name: e.target.value }
                          setSpecialEntityTypes(updated)
                        }}
                        placeholder="Entity name"
                        className="flex-1"
                      />
                      <Input
                        value={entity.description ?? ""}
                        onChange={(e) => {
                          const updated = [...specialEntityTypes]
                          updated[i] = { ...updated[i], description: e.target.value }
                          setSpecialEntityTypes(updated)
                        }}
                        placeholder="Description"
                        className="flex-1"
                      />
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        onClick={() =>
                          setSpecialEntityTypes(specialEntityTypes.filter((_, j) => j !== i))
                        }
                      >
                        <Trash2 className="size-3 text-red-600 dark:text-red-400" />
                      </Button>
                    </div>
                  ))}
                </div>

                <div>
                  <label className="mb-1 block text-xs font-medium">
                    Temperature: {ingestionTemperature.toFixed(1)}
                  </label>
                  <Slider
                    value={[ingestionTemperature]}
                    onValueChange={([v]) => setIngestionTemperature(v)}
                    min={0}
                    max={2}
                    step={0.1}
                  />
                  <p className="mt-1 text-[10px] text-muted-foreground">
                    Lower = more deterministic. Higher = more creative. Default: 1.0
                  </p>
                </div>
              </TabsContent>

              <TabsContent value="chat" className="space-y-4">
                <div>
                  <label className="mb-1 block text-xs font-medium">System Context</label>
                  <Textarea
                    value={chatSystemContext}
                    onChange={(e) => setChatSystemContext(e.target.value)}
                    placeholder="System prompt for chat..."
                    className="min-h-[100px]"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium">Analysis Guidance</label>
                  <Textarea
                    value={chatAnalysisGuidance}
                    onChange={(e) => setChatAnalysisGuidance(e.target.value)}
                    placeholder="Guidance for analysis..."
                    className="min-h-[100px]"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium">
                    Temperature: {chatTemperature.toFixed(1)}
                  </label>
                  <Slider
                    value={[chatTemperature]}
                    onValueChange={([v]) => setChatTemperature(v)}
                    min={0}
                    max={2}
                    step={0.1}
                  />
                </div>
              </TabsContent>

              <TabsContent value="llm" className="space-y-4">
                <div>
                  <label className="mb-1.5 block text-xs font-medium">Provider</label>
                  <div className="flex gap-2">
                    <Button
                      variant={llmProvider === "ollama" ? "primary" : "outline"}
                      size="sm"
                      onClick={() => {
                        setLlmProvider("ollama")
                        const ollamaModels = availableModels.filter((m) => m.provider === "ollama")
                        if (ollamaModels.length > 0) setLlmModelId(ollamaModels[0].id)
                      }}
                      className="flex-1"
                    >
                      Ollama (Local)
                    </Button>
                    <Button
                      variant={llmProvider === "openai" ? "primary" : "outline"}
                      size="sm"
                      onClick={() => {
                        setLlmProvider("openai")
                        const openaiModels = availableModels.filter((m) => m.provider === "openai")
                        if (openaiModels.length > 0) setLlmModelId(openaiModels[0].id)
                      }}
                      className="flex-1"
                    >
                      OpenAI (Remote)
                    </Button>
                  </div>
                </div>

                <div>
                  <label className="mb-1.5 block text-xs font-medium">Model</label>
                  <Select value={llmModelId} onValueChange={setLlmModelId}>
                    <SelectTrigger>
                      <SelectValue placeholder="Select a model..." />
                    </SelectTrigger>
                    <SelectContent>
                      {filteredModels.map((model) => (
                        <SelectItem key={model.id} value={model.id}>
                          {model.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {(() => {
                  const selectedModel = availableModels.find((m) => m.id === llmModelId)
                  if (!selectedModel?.description) return null
                  return (
                    <div className="rounded-md border border-border bg-muted/30 p-3">
                      <p className="text-xs text-muted-foreground">{selectedModel.description}</p>
                      {selectedModel.context_window && (
                        <p className="mt-1 text-[10px] text-muted-foreground">
                          Context: {selectedModel.context_window.toLocaleString()} tokens
                        </p>
                      )}
                    </div>
                  )
                })()}
              </TabsContent>
            </Tabs>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={handleSave}
            disabled={saveMutation.isPending || profileLoading}
          >
            {saveMutation.isPending ? "Saving..." : "Save Profile"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
