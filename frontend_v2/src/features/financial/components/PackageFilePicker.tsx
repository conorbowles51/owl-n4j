import { useRef } from "react"
import { Button } from "@/components/ui/button"

export function PackageFilePicker({
  label,
  button,
  accept,
  files,
  multiple = false,
  disabled,
  onChange,
}: {
  label: string
  button: string
  accept: string
  files: File[]
  multiple?: boolean
  disabled: boolean
  onChange: (files: File[]) => void
}) {
  const input = useRef<HTMLInputElement>(null)
  return (
    <div className="space-y-2 rounded border p-3">
      <p className="font-medium">{label}</p>
      <input
        ref={input}
        type="file"
        hidden
        aria-label={label}
        accept={accept}
        multiple={multiple}
        disabled={disabled}
        onChange={(event) => onChange(Array.from(event.target.files ?? []))}
      />
      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          variant="outline"
          disabled={disabled}
          onClick={() => input.current?.click()}
        >
          {button}
        </Button>
        {files.length > 0 && (
          <Button
            type="button"
            variant="ghost"
            disabled={disabled}
            aria-label={`Clear ${label.toLowerCase()}`}
            onClick={() => {
              if (input.current) input.current.value = ""
              onChange([])
            }}
          >
            Clear selection
          </Button>
        )}
      </div>
      {files.length ? (
        <ul className="list-inside list-disc break-all text-muted-foreground">
          {files.map((file, index) => (
            <li key={index}>{file.name}</li>
          ))}
        </ul>
      ) : (
        <p className="text-muted-foreground">No file selected</p>
      )}
    </div>
  )
}
