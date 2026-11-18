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
 * The app's button. An icon-only button (no words inside) shows the `tooltip` prop, else its title, else its
 * aria-label, as a tooltip that opens on hover and on keyboard focus (lx-guidecover C). A disabled button given a
 * `disabledReason` says why it is disabled and what enables it, in the same tooltip, reachable by keyboard.
 */
type ButtonProps = React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean
    /** Tooltip words; an icon-only button without it uses its aria-label or title. */
    tooltip?: string
    /** Shown while the button is disabled: why, and what enables it. */
    disabledReason?: string
  }

function Button(all: ButtonProps) {
  const { className, variant = "primary", size = "default", asChild = false, tooltip, disabledReason, ...props } = all
  const Comp = asChild ? Slot.Root : "button"
  // already the trigger of a Tooltip the caller drew: never a second one
  const own = (props as Record<string, unknown>)["data-slot"] !== "tooltip-trigger"
  const iconOnly = !hasWords(props.children)
  // the title is the longer explanation when both are given ("Hide this reminder until it changes. This does not
  // complete the work." beside the name "Dismiss ..."): the tooltip shows it, the name stays the aria-label
  const label = (typeof props.title === "string" && props.title ? props.title : undefined) ?? props["aria-label"]
  const off = !!props.disabled && !!disabledReason
  const tip = off ? disabledReason : (tooltip ?? (iconOnly ? label : undefined))
  // The tree keeps one shape across renders (a button that turns enabled, or whose words become a spinner, stays the
  // same element): it is decided by which props are given, never by their values of the moment.
  const holds = "disabledReason" in all
  const named = "aria-label" in props || "title" in props
  const wraps = own && (holds || "tooltip" in all || named)
  const drawn = (
    <Comp
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
      // the tooltip replaces the browser's hover-only title; the name stays for screen readers
      {...(wraps && tip && props.title ? { title: undefined, "aria-label": props["aria-label"] ?? props.title } : null)}
    />
  )
  if (!wraps) return drawn
  return (
    <Tooltip open={tip ? undefined : false}>
      <TooltipTrigger asChild>
        {holds ? (
          // a disabled button takes no hover or focus, so its holder carries the tooltip; the holder keeps the
          // button's own place in the layout (full width, pushed right, growing)
          <span
            tabIndex={off ? 0 : undefined}
            className={cn("inline-flex", holderLayout(className))}
            aria-label={off ? disabledReason : undefined}
            data-slot="disabled-reason"
          >
            {drawn}
          </span>
        ) : (
          drawn
        )}
      </TooltipTrigger>
      {tip && <TooltipContent className="max-w-xs">{tip}</TooltipContent>}
    </Tooltip>
  )
}

/** The layout classes of a button that its holder must carry, so wrapping it moves nothing. */
function holderLayout(className: string | undefined): string {
  return (className ?? "").split(/\s+/).filter((c) => /^(?:[a-z]+:)*(?:w-full|flex-1|grow|shrink-0|ml-auto|mr-auto|mx-auto|self-\S+|justify-self-\S+|col-span-\S+|order-\S+|mt-\S+|mb-\S+|ml-\S+|mr-\S+)$/.test(c)).join(" ")
}

export { Button }
