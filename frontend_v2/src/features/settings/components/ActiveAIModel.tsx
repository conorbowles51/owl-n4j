import { useEffect, useState } from "react"
import { BrainCircuit } from "lucide-react"
import { Link } from "react-router-dom"
import { llmConfigAPI } from "@/features/evidence/api"

export function ActiveAIModel({ workload }: { workload: string }) {
  const [label, setLabel] = useState("Managed AI model")

  useEffect(() => {
    Promise.all([llmConfigAPI.getModels(), llmConfigAPI.getPolicy()])
      .then(([models, policy]) => {
        const configured = policy.configuration[workload]
        const model = models.models.find(
          (candidate) =>
            candidate.id === configured?.model_id &&
            candidate.provider === configured?.provider
        )
        if (model) setLabel(model.name)
      })
      .catch(() => {})
  }, [workload])

  return (
    <Link
      to="/settings/ai"
      title="Managed in AI settings"
      className="inline-flex h-7 items-center gap-1.5 rounded-md border border-border/70 bg-muted/35 px-2 text-[10px] font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
    >
      <BrainCircuit className="size-3" />
      <span className="max-w-36 truncate">{label}</span>
    </Link>
  )
}
