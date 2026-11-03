"use client"

import * as React from "react"

import { cn } from "@/lib/cn"

function Table({
  className,
  density = "comfortable",
  ...props
}: React.ComponentProps<"table"> & {
  /** "dense" for tables to compare (rows of 32 px), "comfortable" for everything else (lx-style F). */
  density?: "comfortable" | "dense"
}) {
  const container = React.useRef<HTMLDivElement>(null)
  const overflowing = useOverflowsSideways(container)
  // A table wider than its panel scrolls sideways; by keyboard only when its scroll area can take focus, so while
  // it overflows the area is a named, focusable region (axe scrollable-region-focusable). The caption is read after
  // the table's content or overflow changes (a ref is not read during render).
  const [captionName, setCaptionName] = React.useState<string | undefined>(undefined)
  React.useLayoutEffect(() => {
    const next = overflowing ? container.current?.querySelector("caption")?.textContent?.trim() || "Table" : undefined
    setCaptionName((prev) => (prev === next ? prev : next))
  }, [overflowing, props.children])
  const name = props["aria-label"] ?? captionName
  return (
    <div
      ref={container}
      data-slot="table-container"
      className="relative w-full overflow-x-auto focus-visible:outline-2 focus-visible:outline-ring"
      {...(overflowing
        ? {
            tabIndex: 0,
            role: "region",
            // Named by what names the table: its labelling elements when it has them, else its label or caption.
            ...(props["aria-labelledby"] ? { "aria-labelledby": props["aria-labelledby"] } : { "aria-label": name }),
          }
        : {})}
    >
      <table
        data-slot="table"
        data-density={density}
        className={cn("type-data w-full caption-bottom text-sm", className)}
        {...props}
      />
    </div>
  )
}

/** True while the element's content is wider than the element; followed as either one changes size. */
function useOverflowsSideways(ref: React.RefObject<HTMLElement | null>) {
  const [overflowing, setOverflowing] = React.useState(false)
  React.useLayoutEffect(() => {
    const element = ref.current
    if (!element) return
    const update = () => setOverflowing(element.scrollWidth > element.clientWidth + 1)
    update()
    if (typeof ResizeObserver === "undefined") return
    const observer = new ResizeObserver(update)
    observer.observe(element)
    if (element.firstElementChild) observer.observe(element.firstElementChild)
    return () => observer.disconnect()
  }, [ref])
  return overflowing
}

function TableHeader({ className, ...props }: React.ComponentProps<"thead">) {
  return (
    <thead
      data-slot="table-header"
      className={cn("[&_tr]:border-b", className)}
      {...props}
    />
  )
}

function TableBody({ className, ...props }: React.ComponentProps<"tbody">) {
  return (
    <tbody
      data-slot="table-body"
      className={cn("[&_tr:last-child]:border-0", className)}
      {...props}
    />
  )
}

function TableFooter({ className, ...props }: React.ComponentProps<"tfoot">) {
  return (
    <tfoot
      data-slot="table-footer"
      className={cn(
        "border-t bg-muted/50 font-medium [&>tr]:last:border-b-0",
        className
      )}
      {...props}
    />
  )
}

function TableRow({ className, ...props }: React.ComponentProps<"tr">) {
  return (
    <tr
      data-slot="table-row"
      className={cn(
        "border-b transition-colors hover:bg-muted/50 data-[state=selected]:bg-muted",
        className
      )}
      {...props}
    />
  )
}

function TableHead({ className, ...props }: React.ComponentProps<"th">) {
  return (
    <th
      data-slot="table-head"
      className={cn(
        "h-row bg-muted/35 px-cell text-left in-data-[density=dense]:h-row-dense align-middle font-semibold whitespace-nowrap text-muted-foreground [&:has([role=checkbox])]:pr-0 [&>[role=checkbox]]:translate-y-[2px]",
        className
      )}
      {...props}
    />
  )
}

function TableCell({ className, ...props }: React.ComponentProps<"td">) {
  return (
    <td
      data-slot="table-cell"
      className={cn(
        "p-cell align-middle whitespace-nowrap in-data-[density=dense]:py-cell-dense [&:has([role=checkbox])]:pr-0 [&>[role=checkbox]]:translate-y-[2px]",
        className
      )}
      {...props}
    />
  )
}

function TableCaption({
  className,
  ...props
}: React.ComponentProps<"caption">) {
  return (
    <caption
      data-slot="table-caption"
      className={cn("mt-4 text-sm text-muted-foreground", className)}
      {...props}
    />
  )
}

export {
  Table,
  TableHeader,
  TableBody,
  TableFooter,
  TableHead,
  TableRow,
  TableCell,
  TableCaption,
}
