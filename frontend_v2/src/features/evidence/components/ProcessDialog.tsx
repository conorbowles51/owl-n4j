import { useState } from "react"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Slider } from "@/components/ui/slider"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { Play } from "lucide-react"
import { useProfiles } from "../hooks/use-profiles"

interface ProcessDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  fileCount: number
  onConfirm: (config: {
    profile?: string
    maxWorkers: number
    imageProvider?: string
  }) => void
  isPending?: boolean
}

export function ProcessDialog({
  open,
  onOpenChange,
  fileCount,
  onConfirm,
  isPending,
}: ProcessDialogProps) {
  const { data: profiles, isLoading: profilesLoading } = useProfiles()
  const [selectedProfile, setSelectedProfile] = useState<string>("")
  const [maxWorkers, setMaxWorkers] = useState(4)
  const [imageProvider, setImageProvider] = useState<string>("")

  const handleConfirm = () => {
    onConfirm({
      profile: selectedProfile || undefined,
      maxWorkers,
      imageProvider: imageProvider || undefined,
    })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Play className="size-4 text-amber-500" />
            Process Evidence
          </DialogTitle>
          <DialogDescription>
            Configure processing for {fileCount} file{fileCount !== 1 ? "s" : ""}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-5 py-2">
          <div>
            <label className="mb-1.5 block text-xs font-medium text-foreground">
              Processing Profile
            </label>
            {profilesLoading ? (
              <div className="flex items-center gap-2 py-2">
                <LoadingSpinner size="sm" />
                <span className="text-xs text-muted-foreground">Loading profiles...</span>
              </div>
            ) : (
              <Select value={selectedProfile} onValueChange={setSelectedProfile}>
                <SelectTrigger>
                  <SelectValue placeholder="Default profile" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value=" ">Default profile</SelectItem>
                  {profiles?.map((p) => (
                    <SelectItem key={p.name} value={p.name}>
                      {p.name}
                      {p.description && (
                        <span className="ml-1 text-muted-foreground">— {p.description}</span>
                      )}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>

          <div>
            <label className="mb-1.5 block text-xs font-medium text-foreground">
              Max Workers: {maxWorkers}
            </label>
            <Slider
              value={[maxWorkers]}
              onValueChange={([v]) => setMaxWorkers(v)}
              min={1}
              max={8}
              step={1}
            />
            <p className="mt-1 text-[10px] text-muted-foreground">
              Number of parallel processing workers
            </p>
          </div>

          <div>
            <label className="mb-1.5 block text-xs font-medium text-foreground">
              Image Provider
            </label>
            <Select value={imageProvider} onValueChange={setImageProvider}>
              <SelectTrigger>
                <SelectValue placeholder="Default (Tesseract)" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value=" ">Default (Tesseract)</SelectItem>
                <SelectItem value="tesseract">Tesseract OCR</SelectItem>
                <SelectItem value="openai">OpenAI Vision</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={handleConfirm}
            disabled={isPending}
          >
            {isPending ? "Starting..." : "Process in Background"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
