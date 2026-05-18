export function SmallEmpty({ label }: { label: string }) {
  return (
    <div className="flex h-full min-h-32 items-center justify-center rounded-md p-6 text-center text-sm text-muted-foreground">
      {label}
    </div>
  )
}
