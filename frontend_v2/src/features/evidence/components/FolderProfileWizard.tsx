import { useState } from "react"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Wand2,
  FileText,
  ChevronRight,
  ChevronLeft,
  Play,
  Check,
  AlertCircle,
} from "lucide-react"
import { useProfiles } from "../hooks/use-profiles"
import {
  useFolderFiles,
  useGenerateFolderProfile,
  useTestFolderProfile,
} from "../hooks/use-folder-profile"
import { toast } from "sonner"

type WizardStep = "mode" | "configure" | "preview" | "test"
type WizardMode = "generate" | "existing"

const FILE_ROLES = [
  { value: "document", label: "Document" },
  { value: "audio", label: "Audio" },
  { value: "metadata", label: "Metadata" },
  { value: "interpretation", label: "Interpretation" },
  { value: "ignore", label: "Ignore" },
]

interface FileRoleOverride {
  filename: string
  role: string
}

interface FolderProfileWizardProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  caseId: string
  folderPath: string
  onComplete?: (config: Record<string, unknown>) => void
}

export function FolderProfileWizard({
  open,
  onOpenChange,
  caseId,
  folderPath,
  onComplete,
}: FolderProfileWizardProps) {
  const [step, setStep] = useState<WizardStep>("mode")
  const [mode, setMode] = useState<WizardMode>("generate")
  const [instructions, setInstructions] = useState("")
  const [profileName, setProfileName] = useState("")
  const [selectedProfile, setSelectedProfile] = useState("")
  const [fileOverrides, setFileOverrides] = useState<FileRoleOverride[]>([])
  const [generatedJson, setGeneratedJson] = useState("")
  const [testResult, setTestResult] = useState<Record<string, unknown> | null>(null)

  const { data: profiles } = useProfiles()
  const { data: folderFiles, isLoading: filesLoading } = useFolderFiles(
    caseId,
    folderPath,
    open
  )
  const generateMutation = useGenerateFolderProfile()
  const testMutation = useTestFolderProfile()

  // Initialize file overrides when folder files load
  const [appliedFiles, setAppliedFiles] = useState<string[] | null>(null)
  if (folderFiles?.length && folderFiles !== appliedFiles) {
    setAppliedFiles(folderFiles)
    setFileOverrides(
      folderFiles.map((f) => ({ filename: f, role: "document" }))
    )
  }

  // Reset on open
  const [prevOpen, setPrevOpen] = useState(false)
  if (open && !prevOpen) {
    setPrevOpen(true)
    setStep("mode")
    setMode("generate")
    setInstructions("")
    setProfileName("")
    setSelectedProfile("")
    setGeneratedJson("")
    setTestResult(null)
  } else if (!open && prevOpen) {
    setPrevOpen(false)
  }

  const STEPS: WizardStep[] = ["mode", "configure", "preview", "test"]
  const stepIndex = STEPS.indexOf(step)

  const stepLabels: Record<WizardStep, string> = {
    mode: "Mode",
    configure: "Configure",
    preview: "Preview",
    test: "Test",
  }

  const canAdvance = () => {
    if (step === "mode") return true
    if (step === "configure") {
      return mode === "generate" ? instructions.trim().length > 0 : !!selectedProfile
    }
    if (step === "preview") return generatedJson.trim().length > 0
    return false
  }

  const handleNext = async () => {
    if (step === "configure" && mode === "generate") {
      // Generate profile from instructions
      generateMutation.mutate(
        {
          case_id: caseId,
          folder_path: folderPath,
          instructions,
          profile_name: profileName || undefined,
        },
        {
          onSuccess: (data) => {
            setGeneratedJson(JSON.stringify(data, null, 2))
            setStep("preview")
          },
          onError: (err) => toast.error(`Generation failed: ${err.message}`),
        }
      )
      return
    }

    if (step === "configure" && mode === "existing") {
      // Build config from existing profile + overrides
      const config = {
        type: "special",
        base_profile: selectedProfile,
        file_rules: fileOverrides
          .filter((f) => f.role !== "document") // Only include non-default overrides
          .map((f) => ({ pattern: f.filename, role: f.role })),
      }
      setGeneratedJson(JSON.stringify(config, null, 2))
      setStep("preview")
      return
    }

    const nextIdx = stepIndex + 1
    if (nextIdx < STEPS.length) {
      setStep(STEPS[nextIdx])
    }
  }

  const handleBack = () => {
    const prevIdx = stepIndex - 1
    if (prevIdx >= 0) {
      setStep(STEPS[prevIdx])
    }
  }

  const handleTest = () => {
    let config: Record<string, unknown>
    try {
      config = JSON.parse(generatedJson)
    } catch {
      toast.error("Invalid JSON — fix the configuration before testing")
      return
    }

    testMutation.mutate(
      {
        case_id: caseId,
        folder_path: folderPath,
        profile_config: config,
      },
      {
        onSuccess: (data) => {
          setTestResult(data)
          toast.success("Test completed")
        },
        onError: (err) => toast.error(`Test failed: ${err.message}`),
      }
    )
  }

  const handleFinish = () => {
    try {
      const config = JSON.parse(generatedJson)
      onComplete?.(config)
      onOpenChange(false)
    } catch {
      toast.error("Invalid JSON configuration")
    }
  }

  const updateOverride = (index: number, role: string) => {
    setFileOverrides((prev) =>
      prev.map((f, i) => (i === index ? { ...f, role } : f))
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[85vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Wand2 className="size-4" />
            Folder Profile Wizard
          </DialogTitle>
        </DialogHeader>

        {/* Step indicators */}
        <div className="flex items-center gap-1 px-1">
          {STEPS.map((s, i) => (
            <div key={s} className="flex items-center gap-1">
              {i > 0 && <ChevronRight className="size-3 text-muted-foreground" />}
              <Badge
                variant={step === s ? "info" : i < stepIndex ? "success" : "slate"}
                className="text-[10px]"
              >
                {stepLabels[s]}
              </Badge>
            </div>
          ))}
        </div>

        <div className="flex-1 overflow-auto space-y-4 py-2">
          {/* Step 1: Mode Selection */}
          {step === "mode" && (
            <div className="space-y-3">
              <p className="text-xs text-muted-foreground">
                Choose how to create the folder profile for{" "}
                <span className="font-mono text-foreground">{folderPath}</span>
              </p>
              <div className="grid grid-cols-2 gap-3">
                <button
                  onClick={() => setMode("generate")}
                  className={`rounded-lg border p-4 text-left transition-colors ${
                    mode === "generate"
                      ? "border-amber-500 bg-amber-500/5"
                      : "border-border hover:border-muted-foreground"
                  }`}
                >
                  <Wand2 className="mb-2 size-5 text-amber-500" />
                  <p className="text-sm font-medium">Generate from Instructions</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Describe how files should be processed and let AI generate the configuration
                  </p>
                </button>
                <button
                  onClick={() => setMode("existing")}
                  className={`rounded-lg border p-4 text-left transition-colors ${
                    mode === "existing"
                      ? "border-amber-500 bg-amber-500/5"
                      : "border-border hover:border-muted-foreground"
                  }`}
                >
                  <FileText className="mb-2 size-5 text-amber-500" />
                  <p className="text-sm font-medium">Use Existing Profile</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Start from an existing profile and customize per-file roles
                  </p>
                </button>
              </div>
            </div>
          )}

          {/* Step 2: Configuration */}
          {step === "configure" && mode === "generate" && (
            <div className="space-y-4">
              <div>
                <label className="mb-1 block text-xs font-medium">
                  Profile Name (optional)
                </label>
                <Input
                  placeholder="e.g., wiretap-folder-profile"
                  value={profileName}
                  onChange={(e) => setProfileName(e.target.value)}
                  className="h-8"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium">
                  Instructions
                </label>
                <Textarea
                  placeholder="Describe how the files in this folder should be processed. For example: 'This folder contains wiretap recordings. MP3 files are phone calls that should be transcribed. PDF files are court documents. The metadata.json contains call details.'"
                  value={instructions}
                  onChange={(e) => setInstructions(e.target.value)}
                  className="min-h-[120px] text-xs"
                />
              </div>
              {folderFiles && (
                <div>
                  <p className="mb-2 text-xs font-medium">
                    Files in folder ({folderFiles.length})
                  </p>
                  <div className="max-h-40 overflow-auto rounded-md border border-border">
                    {folderFiles.map((f) => (
                      <div
                        key={f}
                        className="flex items-center gap-2 border-b border-border px-3 py-1.5 last:border-0"
                      >
                        <FileText className="size-3 text-muted-foreground" />
                        <span className="truncate text-xs">{f}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {step === "configure" && mode === "existing" && (
            <div className="space-y-4">
              <div>
                <label className="mb-1 block text-xs font-medium">Base Profile</label>
                <Select value={selectedProfile} onValueChange={setSelectedProfile}>
                  <SelectTrigger className="h-8 text-xs">
                    <SelectValue placeholder="Select a profile..." />
                  </SelectTrigger>
                  <SelectContent>
                    {profiles?.map((p) => (
                      <SelectItem key={p.name} value={p.name}>
                        {p.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {filesLoading ? (
                <div className="flex justify-center py-6">
                  <LoadingSpinner />
                </div>
              ) : (
                <div>
                  <p className="mb-2 text-xs font-medium">Per-file role overrides</p>
                  <div className="max-h-60 overflow-auto space-y-1">
                    {fileOverrides.map((file, i) => (
                      <div
                        key={file.filename}
                        className="flex items-center gap-2 rounded-md border border-border px-3 py-1.5"
                      >
                        <FileText className="size-3 shrink-0 text-muted-foreground" />
                        <span className="min-w-0 flex-1 truncate text-xs">
                          {file.filename}
                        </span>
                        <Select
                          value={file.role}
                          onValueChange={(v) => updateOverride(i, v)}
                        >
                          <SelectTrigger className="h-6 w-32 text-xs">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {FILE_ROLES.map((r) => (
                              <SelectItem key={r.value} value={r.value}>
                                {r.label}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Step 3: Preview */}
          {step === "preview" && (
            <div className="space-y-3">
              <p className="text-xs text-muted-foreground">
                Review and edit the generated configuration before testing.
              </p>
              <Textarea
                value={generatedJson}
                onChange={(e) => setGeneratedJson(e.target.value)}
                className="min-h-[250px] font-mono text-xs"
              />
            </div>
          )}

          {/* Step 4: Test */}
          {step === "test" && (
            <div className="space-y-4">
              <div className="flex items-center gap-3">
                <Button
                  variant="primary"
                  size="sm"
                  onClick={handleTest}
                  disabled={testMutation.isPending}
                >
                  <Play className="size-3.5" />
                  {testMutation.isPending ? "Testing..." : "Run Test"}
                </Button>
                <p className="text-xs text-muted-foreground">
                  Test the profile configuration against the folder
                </p>
              </div>

              {testResult && (
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    {testResult.success ? (
                      <Check className="size-4 text-green-500" />
                    ) : (
                      <AlertCircle className="size-4 text-red-500" />
                    )}
                    <span className="text-sm font-medium">
                      {testResult.success ? "Test passed" : "Test failed"}
                    </span>
                  </div>
                  <pre className="max-h-48 overflow-auto rounded-md bg-muted p-3 text-xs">
                    {JSON.stringify(testResult, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          )}
        </div>

        <DialogFooter className="flex-row justify-between">
          <div>
            {stepIndex > 0 && (
              <Button variant="outline" size="sm" onClick={handleBack}>
                <ChevronLeft className="size-3.5" />
                Back
              </Button>
            )}
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            {step === "test" ? (
              <Button variant="primary" size="sm" onClick={handleFinish}>
                <Check className="size-3.5" />
                Use Configuration
              </Button>
            ) : (
              <Button
                variant="primary"
                size="sm"
                onClick={handleNext}
                disabled={!canAdvance() || generateMutation.isPending}
              >
                {generateMutation.isPending ? "Generating..." : "Next"}
                <ChevronRight className="size-3.5" />
              </Button>
            )}
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
