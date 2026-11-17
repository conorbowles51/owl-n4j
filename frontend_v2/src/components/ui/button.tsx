import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { Slot } from "radix-ui"

import { cn } from "@/lib/cn"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { hasWords } from "@/components/ui/has-words"

const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-1.5 rounded-md text-[13px] font-semibold whitespace-nowrap transition-[background-color,border-color,color,box-shadow,transform] duration-200 ease-[var(--ease-loupe)] outline-none focus-visible:ring-2 focus-visible:ring-ring/40 focus-visible:ring-offset-2 focus-visible:ring-offset-background active:translate-y-px disabled:pointer-events-none disabled:opacity-50 disabled:active:translate-y-0 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        primary:
          "border border-primary bg-primary text-primary-foreground shadow-[0_8px_18px_-10px_rgba(180,22,36,0.8)] hover:bg-primary/90 hover:shadow-[0_10px_24px_-12px_rgba(180,22,36,0.72)] active:bg-primary/80",
        secondary:
          "border border-secondary bg-secondary text-secondary-foreground hover:border-border hover:bg-secondary/80",
        outline:
          "border border-input bg-background text-foreground shadow-xs hover:border-ring/35 hover:bg-accent hover:text-accent-foreground",
        ghost:
          "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
        danger:
          "border border-destructive/80 bg-destructive text-destructive-foreground hover:bg-destructive/90 active:bg-destructive/80",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        sm: "h-7 px-2.5 text-xs",
        default: "h-8 px-3.5 text-[13px]",
        lg: "h-9 px-5 text-sm",
        icon: "h-8 w-8",
        "icon-sm": "h-7 w-7",
        "icon-lg": "h-9 w-9",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "default",
    },
  }
)

/**
 * The app's button. An icon-only button (no words inside) shows its name, the `tooltip` prop or else its aria-label
 * or title, as a tooltip that opens on hover and on keyboard focus (lx-guidecover C). A disabled button given a
 * `disabledReason` says why it is disabled and what enables it, in the same tooltip, reachable by keyboard.
 */
function Button({
  className,
  variant = "primary",
  size = "default",
  asChild = false,
  tooltip,
  disabledReason,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean
    /** Tooltip words; an icon-only button without it uses its aria-label or title. */
    tooltip?: string
    /** Shown while the button is disabled: why, and what enables it. */
    disabledReason?: string
  }) {
  const Comp = asChild ? Slot.Root : "button"
  // already the trigger of a Tooltip the caller drew: never a second one
  const own = (props as Record<string, unknown>)["data-slot"] !== "tooltip-trigger"
  const iconOnly = !hasWords(props.children)
  const label = props["aria-label"] ?? (typeof props.title === "string" ? props.title : undefined)
  const off = !!props.disabled && !!disabledReason
  const tip = off ? disabledReason : (tooltip ?? (iconOnly ? label : undefined))
  const drawn = (
    <Comp
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
      // the tooltip replaces the browser's hover-only title; the name stays for screen readers
      {...(own && tip && props.title ? { title: undefined, "aria-label": props["aria-label"] ?? props.title } : null)}
    />
  )
  if (!own || !tip) return drawn
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        {off ? (
          // a disabled button takes no hover or focus, so its holder carries the tooltip
          <span tabIndex={0} className="inline-flex" aria-label={disabledReason} data-slot="disabled-reason">
            {drawn}
          </span>
        ) : (
          drawn
        )}
      </TooltipTrigger>
      <TooltipContent className="max-w-xs">{tip}</TooltipContent>
    </Tooltip>
  )
}

export { Button }
