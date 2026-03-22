import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/cn"
import { ChevronRight, Layers, FolderOpen } from "lucide-react"
import type { ProfileChainLink } from "@/types/evidence.types"

interface ProfileChainPreviewProps {
  chain: ProfileChainLink[]
}

export function ProfileChainPreview({ chain }: ProfileChainPreviewProps) {
  if (chain.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-slate-300 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-900/50">
        <p className="text-center text-xs text-muted-foreground">
          No inherited context. This folder has no parent profile chain.
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
        <Layers className="size-3.5" />
        Profile Inheritance Chain
      </div>
      <div className="flex items-stretch gap-0 overflow-x-auto pb-1">
        {chain.map((link, index) => {
          const hasContext = !!link.context_instructions
          const hasOverrides = !!link.profile_overrides && Object.keys(link.profile_overrides).length > 0
          const isActive = hasContext || hasOverrides
          const isLast = index === chain.length - 1

          return (
            <div key={link.folder_id} className="flex shrink-0 items-center">
              <div
                className={cn(
                  "relative flex min-w-[140px] max-w-[200px] flex-col gap-1.5 rounded-md border p-2.5",
                  isActive
                    ? "border-amber-500/40 bg-amber-500/5 dark:border-amber-500/30 dark:bg-amber-500/5"
                    : "border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-800/50"
                )}
              >
                <div className="flex items-center gap-1.5">
                  <FolderOpen
                    className={cn(
                      "size-3 shrink-0",
                      isActive
                        ? "text-amber-600 dark:text-amber-400"
                        : "text-slate-400 dark:text-slate-500"
                    )}
                  />
                  <span className="truncate text-xs font-medium text-foreground">
                    {link.folder_name}
                  </span>
                </div>

                {hasContext ? (
                  <p className="line-clamp-2 text-[10px] leading-relaxed text-muted-foreground">
                    {link.context_instructions}
                  </p>
                ) : (
                  <p className="text-[10px] italic text-slate-400 dark:text-slate-600">
                    No context set
                  </p>
                )}

                {hasOverrides && (
                  <div className="flex flex-wrap gap-1">
                    {link.profile_overrides?.special_entity_types?.length ? (
                      <Badge variant="amber" className="text-[9px] px-1.5 py-0">
                        {link.profile_overrides.special_entity_types.length} entity type{link.profile_overrides.special_entity_types.length !== 1 ? "s" : ""}
                      </Badge>
                    ) : null}
                    {link.profile_overrides?.temperature !== undefined && (
                      <Badge variant="slate" className="text-[9px] px-1.5 py-0">
                        temp {link.profile_overrides.temperature}
                      </Badge>
                    )}
                  </div>
                )}
              </div>

              {!isLast && (
                <ChevronRight className="mx-1 size-3.5 shrink-0 text-slate-300 dark:text-slate-600" />
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
