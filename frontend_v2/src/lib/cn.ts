import { type ClassValue, clsx } from "clsx"
import { extendTailwindMerge } from "tailwind-merge"

/**
 * tailwind-merge with the theme's own spacing names (lx-style F: cell, row, panel, stack and their dense or
 * reading forms). Without them a caller's p-0 or h-8 would not replace the shared p-cell or h-row default.
 */
const twMerge = extendTailwindMerge({
  extend: {
    theme: {
      spacing: ["cell", "cell-dense", "row", "row-dense", "panel", "panel-reading", "stack", "stack-reading"],
    },
  },
})

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
