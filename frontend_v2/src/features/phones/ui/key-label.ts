/** Human key names for the overlay. */
export function keyLabel(key: string): string {
  return key
    .split(" ")
    .map((part) =>
      part
        .replace("Mod+", "Ctrl/Cmd+")
        .replace("ArrowDown", "Down arrow")
        .replace("ArrowUp", "Up arrow")
        .replace("Escape", "Esc")
        .replace(/^ $/, "Space")
    )
    .join(" then ")
}
