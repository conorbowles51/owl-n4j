# Frontend Design System — Owl

**Document:** Frontend Architecture & Component Strategy
**Last Updated:** 2026-03-05
**Status:** Draft
**Depends On:** Brand Kit (brand-kit.html)

---

## 1. Overview

This document defines how we build the Owl frontend: the component library strategy, the relationship between shadcn/ui and our brand, the thin abstraction layer that ensures consistency, and the conventions every developer must follow. The goal is a frontend that is visually distinctive, consistent across every screen, and fast to develop against.

**The core principle:** shadcn/ui gives us excellent, accessible, unstyled primitives. We wrap them in a thin brand layer that applies Owl's design tokens (colors, typography, spacing, radii, shadows). Developers never use raw shadcn components directly — they import from our `@owl/ui` layer, which ensures brand compliance by default.

---

## 2. Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| Language | TypeScript (strict mode) | Type safety across the codebase |
| Framework | React 19 | UI rendering |
| Build | Vite | Fast builds, HMR |
| Styling | Tailwind CSS 4 | Utility-first CSS |
| Components | shadcn/ui | Accessible primitive components |
| Brand Layer | `@owl/ui` (internal) | Thin wrapper applying brand tokens |
| State (server) | TanStack Query v5 | Data fetching, caching, revalidation |
| State (client) | Zustand | Global client state |
| Routing | React Router v7 | Route-based code splitting |
| Icons | Lucide React | Consistent iconography |
| Charts | Recharts or Tremor | Data visualization |
| Graph Viz | Cytoscape.js or D3.js | Knowledge graph rendering |
| Forms | React Hook Form + Zod | Validation |
| Animation | Framer Motion (sparingly) | Purposeful transitions only |

---

## 3. The Brand Layer: `@owl/ui`

### 3.1 Why a Wrapper Layer?

shadcn/ui is intentionally unstyled — it gives you copy-paste components that you're meant to customize. This is great for flexibility but dangerous for consistency. Without a wrapper:

- Developers might use different color classes on the same component type.
- Button variants proliferate without a single source of truth.
- The brand evolves (say we tweak the amber accent) and now we're hunting through 200 files to update.

The wrapper solves this by being the **single place where brand decisions are made**. It's thin — typically 5-30 lines per component — but it's the law.

### 3.2 Architecture

```
src/
├── components/
│   └── ui/                    ← @owl/ui — the brand layer
│       ├── button.tsx         ← wraps shadcn Button + brand variants
│       ├── badge.tsx          ← wraps shadcn Badge + Owl status colors
│       ├── card.tsx           ← wraps shadcn Card + dark/light surface logic
│       ├── input.tsx          ← wraps shadcn Input + amber focus ring
│       ├── dialog.tsx         ← wraps shadcn Dialog + backdrop, animation
│       ├── data-table.tsx     ← wraps shadcn Table + dense data styling
│       ├── sidebar.tsx        ← custom — Owl navigation sidebar
│       ├── node-badge.tsx     ← custom — entity type badge with graph colors
│       ├── entity-card.tsx    ← custom — entity display card
│       ├── status-indicator.tsx ← custom — processing/evidence status
│       └── ...
├── features/                  ← Feature-based organization
│   ├── cases/
│   ├── evidence/
│   ├── graph/
│   ├── timeline/
│   ├── chat/
│   └── ...
├── lib/
│   ├── theme.ts              ← Owl token definitions
│   ├── cn.ts                 ← className utility (clsx + tailwind-merge)
│   └── utils.ts
└── styles/
    └── globals.css            ← CSS variables, Tailwind config, base styles
```

### 3.3 How It Works: Example

**Raw shadcn Button** (what you get from `npx shadcn-ui add button`):

```tsx
// Generic, no brand opinion
<Button variant="default" size="default">Click me</Button>
```

**Owl Button** (what developers actually use):

```tsx
// src/components/ui/button.tsx
import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/cn"

const buttonVariants = cva(
  // Base styles — Owl specific
  "inline-flex items-center justify-center gap-1.5 rounded-[6px] font-semibold " +
  "transition-all duration-200 ease-[cubic-bezier(0.25,0.1,0.25,1)] " +
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500/40 " +
  "focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950 " +
  "disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        // Primary: Amber — for main CTAs
        primary:
          "bg-amber-500 text-white hover:bg-amber-400 active:bg-amber-600",
        // Secondary: Slate 900 — for important but secondary actions
        secondary:
          "bg-slate-900 text-slate-50 hover:bg-slate-800 " +
          "dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-200",
        // Outline: bordered — for tertiary actions
        outline:
          "border border-slate-300 bg-transparent text-slate-700 " +
          "hover:bg-slate-50 hover:border-slate-400 " +
          "dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-800",
        // Ghost: no border — for inline actions, toolbar items
        ghost:
          "text-slate-500 hover:bg-slate-100 hover:text-slate-700 " +
          "dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200",
        // Danger: destructive actions
        danger:
          "bg-red-500 text-white hover:bg-red-600 active:bg-red-700",
        // Link: text-only with underline
        link:
          "text-amber-500 underline-offset-4 hover:underline",
      },
      size: {
        sm: "h-7 px-2.5 text-xs",
        default: "h-8 px-3.5 text-[13px]",
        lg: "h-9 px-5 text-sm",
        icon: "h-8 w-8",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "default",
    },
  }
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button"
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    )
  }
)
Button.displayName = "Button"

export { Button, buttonVariants }
```

**Usage in feature code:**

```tsx
import { Button } from "@/components/ui/button"

// Developers don't think about colors — they think about intent
<Button variant="primary">Process Evidence</Button>
<Button variant="outline">Export Report</Button>
<Button variant="danger" size="sm">Delete Case</Button>
<Button variant="ghost" size="icon"><SearchIcon /></Button>
```

### 3.4 Custom Owl Components

Some components don't exist in shadcn and are unique to our domain:

**NodeBadge** — Entity type badge with graph palette colors:

```tsx
// src/components/ui/node-badge.tsx
import { cn } from "@/lib/cn"
import { nodeColors, type EntityType } from "@/lib/theme"

interface NodeBadgeProps {
  type: EntityType
  className?: string
  children?: React.ReactNode
}

export function NodeBadge({ type, className, children }: NodeBadgeProps) {
  const color = nodeColors[type]
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5",
        "text-[11px] font-semibold",
        className
      )}
      style={{
        backgroundColor: `${color}15`,
        color: color,
      }}
    >
      <span
        className="h-2 w-2 rounded-full"
        style={{ backgroundColor: color }}
      />
      {children ?? type}
    </span>
  )
}
```

**StatusIndicator** — Evidence processing status:

```tsx
// src/components/ui/status-indicator.tsx
const statusConfig = {
  processed:   { color: "success", label: "Processed" },
  processing:  { color: "amber",   label: "Processing" },
  queued:      { color: "slate",   label: "Queued" },
  failed:      { color: "danger",  label: "Failed" },
  unprocessed: { color: "slate",   label: "Unprocessed" },
} as const

export function StatusIndicator({ status }: { status: keyof typeof statusConfig }) {
  const config = statusConfig[status]
  return <Badge variant={config.color}>{config.label}</Badge>
}
```

---

## 4. Theme Token System

### 4.1 globals.css — The Source of Truth

All Owl design tokens are defined as CSS custom properties. This is the single source of truth that both Tailwind classes and direct CSS reference.

```css
/* src/styles/globals.css */
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    /* Surfaces */
    --background: 0 0% 100%;
    --foreground: 215 28% 10%;
    --card: 0 0% 100%;
    --card-foreground: 215 28% 10%;
    --popover: 0 0% 100%;
    --popover-foreground: 215 28% 10%;

    /* Primary (Amber) */
    --primary: 39 91% 44%;
    --primary-foreground: 0 0% 100%;

    /* Secondary (Slate) */
    --secondary: 215 16% 95%;
    --secondary-foreground: 215 28% 10%;

    /* Muted */
    --muted: 215 16% 95%;
    --muted-foreground: 215 10% 46%;

    /* Accent */
    --accent: 215 16% 95%;
    --accent-foreground: 215 28% 10%;

    /* Destructive */
    --destructive: 0 84% 60%;
    --destructive-foreground: 0 0% 100%;

    /* Focus ring: Amber */
    --ring: 39 91% 44%;

    /* Border & Input */
    --border: 215 16% 85%;
    --input: 215 16% 85%;

    /* Radius — Owl default */
    --radius: 0.375rem;
  }

  .dark {
    --background: 224 43% 7%;
    --foreground: 210 40% 96%;
    --card: 222 47% 9%;
    --card-foreground: 210 40% 96%;
    --popover: 222 47% 9%;
    --popover-foreground: 210 40% 96%;

    --primary: 39 91% 44%;
    --primary-foreground: 0 0% 100%;

    --secondary: 217 25% 18%;
    --secondary-foreground: 210 40% 96%;

    --muted: 217 25% 18%;
    --muted-foreground: 215 16% 57%;

    --accent: 217 25% 18%;
    --accent-foreground: 210 40% 96%;

    --destructive: 0 84% 60%;
    --destructive-foreground: 0 0% 100%;

    --ring: 39 91% 44%;

    --border: 215 25% 22%;
    --input: 215 25% 22%;
  }
}
```

### 4.2 theme.ts — Token Definitions in TypeScript

```typescript
// src/lib/theme.ts

export const nodeColors = {
  person:        "#6366F1",
  organization:  "#8B5CF6",
  location:      "#14B8A6",
  financial:     "#F59E0B",
  document:      "#64748B",
  event:         "#EC4899",
  communication: "#06B6D4",
  vehicle:       "#84CC16",
  digital:       "#A855F7",
  evidence:      "#F97316",
} as const

export type EntityType = keyof typeof nodeColors

export const statusColors = {
  success: { bg: "#DCFCE7", text: "#15803D", dot: "#22C55E" },
  danger:  { bg: "#FEE2E2", text: "#B91C1C", dot: "#EF4444" },
  warning: { bg: "#FEF9C3", text: "#A16207", dot: "#EAB308" },
  info:    { bg: "#DBEAFE", text: "#1D4ED8", dot: "#3B82F6" },
  amber:   { bg: "#FBF0D0", text: "#92610A", dot: "#D4920A" },
  slate:   { bg: "#E8ECF1", text: "#3E4C63", dot: "#8494A7" },
} as const

export type StatusVariant = keyof typeof statusColors
```

---

## 5. Tailwind Configuration

```typescript
// tailwind.config.ts
import type { Config } from "tailwindcss"

const config: Config = {
  darkMode: "class",
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Owl brand slate (overrides Tailwind defaults)
        slate: {
          950: "#0B0F1A",
          900: "#111827",
          800: "#1E293B",
          700: "#2D3A4F",
          600: "#3E4C63",
          500: "#5A6A82",
          400: "#8494A7",
          300: "#AAB7C7",
          200: "#CDD5DF",
          100: "#E8ECF1",
          50:  "#F4F6F8",
        },
        // Owl amber accent
        amber: {
          500: "#D4920A",
          400: "#E5A61B",
          300: "#F0BD4F",
          200: "#F7D88A",
          100: "#FBF0D0",
          50:  "#FEFAF0",
        },
        // Graph node palette
        node: {
          person:        "#6366F1",
          organization:  "#8B5CF6",
          location:      "#14B8A6",
          financial:     "#F59E0B",
          document:      "#64748B",
          event:         "#EC4899",
          communication: "#06B6D4",
          vehicle:       "#84CC16",
          digital:       "#A855F7",
          evidence:      "#F97316",
        },
        // shadcn/ui semantic tokens (CSS variable references)
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
      },
      fontFamily: {
        sans: ["Inter", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "sans-serif"],
        mono: ["JetBrains Mono", "Fira Code", "SF Mono", "monospace"],
      },
      fontSize: {
        xs:   ["0.75rem",    { lineHeight: "1rem" }],
        sm:   ["0.8125rem",  { lineHeight: "1.25rem" }],
        base: ["0.875rem",   { lineHeight: "1.375rem" }],
        lg:   ["1rem",       { lineHeight: "1.5rem" }],
        xl:   ["1.125rem",   { lineHeight: "1.625rem" }],
        "2xl":["1.375rem",   { lineHeight: "1.75rem" }],
        "3xl":["1.75rem",    { lineHeight: "2.125rem" }],
        "4xl":["2.25rem",    { lineHeight: "2.5rem" }],
      },
      borderRadius: {
        sm:  "0.25rem",
        md:  "0.375rem",
        lg:  "0.5rem",
        xl:  "0.75rem",
      },
      boxShadow: {
        sm: "0 1px 2px 0 rgba(0,0,0,0.05)",
        md: "0 2px 8px -1px rgba(0,0,0,0.08), 0 1px 3px -1px rgba(0,0,0,0.06)",
        lg: "0 8px 24px -4px rgba(0,0,0,0.10), 0 2px 8px -2px rgba(0,0,0,0.06)",
        xl: "0 16px 48px -8px rgba(0,0,0,0.12), 0 4px 16px -4px rgba(0,0,0,0.08)",
      },
      transitionTimingFunction: {
        owl: "cubic-bezier(0.25, 0.1, 0.25, 1.0)",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
}

export default config
```

---

## 6. Component Inventory

### 6.1 shadcn/ui Components to Install

These are the shadcn primitives we'll wrap:

| Component | Owl Wrapper | Usage |
|---|---|---|
| Button | `Button` with branded variants | CTAs, actions, toolbar items |
| Badge | `Badge` + `NodeBadge` + `StatusIndicator` | Entity types, status, roles |
| Card | `Card` with dark/light surface | Case cards, entity cards, panels |
| Dialog | `Dialog` with branded backdrop | Modals (create case, merge entities) |
| Sheet | `Sheet` for side panels | Node details, chat panel, evidence viewer |
| DropdownMenu | `DropdownMenu` | Context menus, action menus |
| Command | `CommandPalette` | Global search (Cmd+K) |
| Table | `DataTable` with dense styling | Evidence list, entity list, audit log |
| Tabs | `Tabs` | View switcher (Graph, Timeline, Map, etc.) |
| Input | `Input` with amber focus ring | Search, forms, Cypher input |
| Select | `Select` | Dropdowns (profile, model, filters) |
| Textarea | `Textarea` | Notes, descriptions, chat input |
| Tooltip | `Tooltip` | Help text, truncated labels |
| Popover | `Popover` | Filters, date pickers |
| Avatar | `Avatar` | User presence indicators |
| Progress | `Progress` | Ingestion progress bars |
| Skeleton | `Skeleton` | Loading states |
| Toast | `Toast` (Sonner) | Notifications |
| Separator | `Separator` | Visual dividers |
| ScrollArea | `ScrollArea` | Scrollable panels |
| Accordion | `Accordion` | Collapsible sections |
| Checkbox | `Checkbox` | Multi-select in tables |
| Switch | `Switch` | Toggle settings |
| Slider | `Slider` | Confidence thresholds, date ranges |
| ContextMenu | `ContextMenu` | Right-click on graph nodes |
| ResizablePanel | `ResizablePanel` | Split views (graph + details) |

### 6.2 Custom Owl Components (Not from shadcn)

| Component | Purpose |
|---|---|
| `AppSidebar` | Main navigation sidebar with Owl branding |
| `CaseCard` | Case list item with status, members, metadata |
| `EntityCard` | Entity display with type badge, connections count, actions |
| `NodeBadge` | Entity type badge using graph palette |
| `StatusIndicator` | Processing status with color coding |
| `GraphCanvas` | Cytoscape.js/D3 graph renderer with Owl styling |
| `TimelineTrack` | Timeline visualization component |
| `MapContainer` | Geographic map with entity pins |
| `ChatMessage` | AI chat message with citations |
| `EvidenceRow` | Evidence file row with status and actions |
| `PresenceIndicator` | Active user avatar stack |
| `CypherInput` | Monospaced code input for Cypher queries |
| `ConfidenceBar` | Visual confidence score indicator |
| `CostBadge` | LLM cost display (formatted currency) |
| `EmptyState` | Standardized empty state with illustration |
| `PageHeader` | Consistent page header with breadcrumbs and actions |

---

## 7. Dark Mode Strategy

### 7.1 Default Dark

Owl defaults to dark mode. The `<html>` element gets `class="dark"` by default. Users can toggle to light mode via settings.

```tsx
// src/lib/theme-provider.tsx
import { createContext, useContext, useEffect, useState } from "react"

type Theme = "dark" | "light" | "system"

const ThemeContext = createContext<{
  theme: Theme
  setTheme: (theme: Theme) => void
}>({ theme: "dark", setTheme: () => {} })

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = useState<Theme>(
    () => (localStorage.getItem("owl-theme") as Theme) ?? "dark"
  )

  useEffect(() => {
    const root = document.documentElement
    root.classList.remove("dark", "light")

    if (theme === "system") {
      const systemDark = window.matchMedia("(prefers-color-scheme: dark)").matches
      root.classList.add(systemDark ? "dark" : "light")
    } else {
      root.classList.add(theme)
    }

    localStorage.setItem("owl-theme", theme)
  }, [theme])

  return (
    <ThemeContext.Provider value={{ theme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  )
}

export const useTheme = () => useContext(ThemeContext)
```

### 7.2 Component Dark Mode Pattern

Every branded component must handle both themes using Tailwind's `dark:` prefix:

```tsx
// This card automatically adapts
<div className="bg-white border-slate-200 dark:bg-slate-900 dark:border-slate-700">
  <h3 className="text-slate-900 dark:text-slate-50">Entity Name</h3>
  <p className="text-slate-500 dark:text-slate-400">Description</p>
</div>
```

The CSS variable approach in globals.css means shadcn components automatically theme correctly. Our custom components use the Tailwind `dark:` prefix for any hardcoded colors.

---

## 8. Layout Architecture

### 8.1 App Shell

```
┌─────────────────────────────────────────────────────────┐
│ AppSidebar (56px collapsed, 240px expanded)             │
│ ┌──────┬────────────────────────────────────────────┐   │
│ │      │  PageHeader (breadcrumbs + actions)         │   │
│ │ Nav  │────────────────────────────────────────────│   │
│ │ Icons│  Main Content Area                         │   │
│ │      │  (varies by route)                         │   │
│ │      │                                            │   │
│ │      │  ┌────────────┐ ┌────────────────────────┐ │   │
│ │      │  │  Primary   │ │  Detail Panel          │ │   │
│ │      │  │  Content   │ │  (resizable sheet)     │ │   │
│ │      │  └────────────┘ └────────────────────────┘ │   │
│ └──────┴────────────────────────────────────────────┘   │
│                                                         │
│ CommandPalette (Cmd+K overlay)                          │
│ Toast notifications (bottom-right)                      │
└─────────────────────────────────────────────────────────┘
```

### 8.2 Route Structure

```
/                           → Dashboard (case overview)
/cases                      → Case list
/cases/:id                  → Case detail (redirects to graph)
/cases/:id/graph            → Graph view (primary investigation view)
/cases/:id/timeline         → Timeline view
/cases/:id/map              → Map view
/cases/:id/evidence         → Evidence management
/cases/:id/evidence/:fileId → Evidence detail/viewer
/cases/:id/chat             → AI chat
/cases/:id/reports          → Reports list
/cases/:id/reports/:id      → Report detail
/cases/:id/workspace        → Case context, witnesses, theories, tasks
/cases/:id/settings         → Case settings, members, permissions
/admin                      → Admin dashboard
/admin/users                → User management
/admin/usage                → Usage analytics
/admin/profiles             → Profile management
/settings                   → Personal settings (theme, preferences)
```

### 8.3 Responsive Approach

Owl is desktop-first (investigators primarily work on large screens), but must remain usable on tablets for field work:

- **Desktop (1280px+):** Full layout with expanded sidebar, split panels, graph + detail side-by-side.
- **Tablet (768px-1279px):** Collapsed sidebar (icon-only), detail panels as overlays instead of side-by-side.
- **Mobile (< 768px):** Not a primary target, but the layout should not break. Stack everything vertically, sheet panels become full-screen modals.

---

## 9. Developer Conventions

### 9.1 Import Rules

```tsx
// CORRECT — import from the brand layer
import { Button } from "@/components/ui/button"
import { NodeBadge } from "@/components/ui/node-badge"
import { Card, CardHeader, CardContent } from "@/components/ui/card"

// WRONG — never import raw shadcn primitives directly
import { Button } from "@radix-ui/react-button"  // NO
```

### 9.2 Color Rules

- Never use arbitrary Tailwind colors (e.g., `bg-blue-500`). Always use the Owl palette (`bg-slate-*`, `bg-amber-*`, `text-node-person`).
- For semantic status, use the status system (`success`, `danger`, `warning`, `info`), never hardcoded reds/greens.
- For entity types, always use `nodeColors` from the theme, never arbitrary colors.

### 9.3 Typography Rules

- All UI text uses `font-sans` (Inter). Never use serif fonts.
- All code, Cypher, IDs, amounts, and timestamps use `font-mono`.
- Base text size is `text-base` (14px). Never go below `text-xs` (12px).
- Headings use `tracking-tight` for tighter letter-spacing.
- Body text uses `leading-normal` (1.5 line-height).

### 9.4 File Naming

- Components: `PascalCase.tsx` (e.g., `EntityCard.tsx`)
- Utilities: `camelCase.ts` (e.g., `formatCurrency.ts`)
- Hooks: `use-kebab-case.ts` (e.g., `use-case-permissions.ts`)
- Types: `kebab-case.types.ts` (e.g., `case.types.ts`)
- Test files: `*.test.tsx` / `*.test.ts`

### 9.5 Component Anatomy

Every Owl UI component follows this pattern:

```tsx
// 1. Imports
import * as React from "react"
import { cn } from "@/lib/cn"

// 2. Types
interface EntityCardProps {
  entity: Entity
  className?: string
  onClick?: () => void
}

// 3. Component (forwardRef if it wraps a DOM element)
export function EntityCard({ entity, className, onClick }: EntityCardProps) {
  return (
    <div
      className={cn(
        // Base styles
        "flex items-center gap-3 rounded-lg border p-3",
        "bg-white dark:bg-slate-900",
        "border-slate-200 dark:border-slate-700",
        "transition-colors duration-200",
        "hover:border-slate-300 dark:hover:border-slate-600",
        "cursor-pointer",
        // Allow consumer overrides
        className
      )}
      onClick={onClick}
    >
      <NodeBadge type={entity.type} />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-slate-900 dark:text-slate-50 truncate">
          {entity.name}
        </p>
        <p className="text-xs text-slate-500 dark:text-slate-400">
          {entity.connectionCount} connections
        </p>
      </div>
    </div>
  )
}
```

---

## 10. Data Density Philosophy

Investigation UIs need to be dense. Investigators are trained professionals who want to see as much relevant information as possible without scrolling. This means:

- **14px base font** (not 16px). This lets more text fit without sacrificing readability.
- **Compact spacing** in data views (tables, lists, entity panels). Use `space-2` (8px) between rows, not `space-4`.
- **No excessive whitespace.** Cards and panels should use `p-3` or `p-4`, not `p-6` or `p-8`.
- **Information hierarchy through typography weight and color**, not through whitespace.
- **Truncation with tooltips.** Long entity names, file paths, and descriptions truncate with `...` and show full text on hover.
- **Split panels over navigation.** Use resizable split views so users can see the graph AND the detail panel simultaneously, rather than navigating between pages.
- **Keyboard-first.** Power users navigate by keyboard. Every action should have a shortcut. The command palette (Cmd+K) is the primary discovery mechanism.

---

## 11. Accessibility

- All interactive elements must be keyboard-navigable.
- Color is never the only indicator of state — always pair with text, icons, or patterns.
- WCAG AA contrast ratios (4.5:1 for text, 3:1 for large text and UI components).
- All images and icons have appropriate `alt` text or `aria-label`.
- Focus states are visible and use the amber ring consistently.
- Screen reader support via proper ARIA attributes on custom components.
- Reduced motion: respect `prefers-reduced-motion` — disable Framer Motion animations.

---

## 12. Performance Targets

| Metric | Target | Measurement |
|---|---|---|
| First Contentful Paint | < 1.2s | Lighthouse |
| Largest Contentful Paint | < 2.0s | Lighthouse |
| Time to Interactive | < 2.5s | Lighthouse |
| Bundle size (initial) | < 200KB gzipped | Vite build |
| Graph render (1000 nodes) | < 500ms | Custom metric |
| Graph render (10000 nodes) | < 2s | Custom metric |
| Route transition | < 100ms | Perceived |

Achieve these through: route-based code splitting, lazy loading of heavy views (graph, map), virtual scrolling in data tables, Web Workers for graph layout computation, and aggressive tree-shaking.

---

## 13. Next Steps

1. Initialize the React + TypeScript + Vite project.
2. Install and configure Tailwind CSS with the Owl theme.
3. Install shadcn/ui CLI and add base components.
4. Create the `@owl/ui` wrapper layer for the first 10 components.
5. Build the AppSidebar and route structure.
6. Implement the ThemeProvider with dark mode default.
7. Build the case list page as the first complete feature.
8. Set up Storybook for the component library.
