# DKT-478 Shortcuts Verification

Date: 2026-07-17

Scope: personal Settings keyboard shortcut reference in `frontend_v2`, plus the shortcut hints shown in the case sidebar.

## Result

Pass. Settings now renders from `frontend_v2/src/lib/shortcuts-registry.ts`, which only exposes implemented shortcuts. Fabricated or dead entries were removed from the release UI:

- `Ctrl+K` command palette: removed; the global dispatcher had no listener.
- `Ctrl+S` save: removed; no handler exists.
- `Delete` delete selected: removed; graph deletion intentionally requires the context menu confirmation flow.

Browser-conflicting shortcuts were remediated before exposure:

- Case view switching moved from `Ctrl/Cmd+1` through `Ctrl/Cmd+8` to `Ctrl/Cmd+Shift+1` through `Ctrl/Cmd+Shift+8`, avoiding Chrome/Edge tab switching.
- Timeline cluster navigation moved from `Alt+Left/Right` to `Ctrl+Shift+Left/Right`, avoiding browser back/forward navigation.

`aria-keyshortcuts` is now attached to the case sidebar route links for the global case view shortcuts.

## Evidence

Automated checks run in `frontend_v2`:

```text
npm run test -- --project unit src/lib/__tests__/shortcuts-registry.test.ts src/hooks/__tests__/use-keyboard-shortcuts.test.tsx src/hooks/__tests__/use-global-shortcuts.test.ts
```

Result: 3 test files passed, 8 tests passed.

```text
npm run typecheck
```

Result: passed.

```text
npx eslint src/lib/shortcuts-registry.ts src/hooks/use-keyboard-shortcuts.ts src/hooks/use-global-shortcuts.ts src/components/ui/sidebar.tsx src/features/settings/components/SettingsPage.tsx src/features/timeline/hooks/use-keyboard-navigation.ts src/lib/__tests__/shortcuts-registry.test.ts src/hooks/__tests__/use-keyboard-shortcuts.test.tsx src/hooks/__tests__/use-global-shortcuts.test.ts
```

Result: passed.

```text
npm run build
```

Result: passed. Vite emitted existing bundle-size and dynamic/static import warnings; no build failure.

Dependency note: this worktree initially had no installed `node_modules`, so `npm ci` was run against the committed lockfile before verification. `npm ci` reported existing audit findings: 2 low, 4 moderate, 8 high, 4 critical. No dependency versions were changed.

## Blocking Tickets

None created. The mismatches identified for this task were either removed from Settings or remediated in the implemented shortcut behavior.
