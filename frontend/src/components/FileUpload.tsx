import { useCallback, useState } from "react"
import { Upload, FileText } from "lucide-react"
import { cn } from "@/lib/utils"

interface FileUploadProps {
  onFileSelect: (file: File) => void
  accept?: string
  isUploading?: boolean
}

export default function FileUpload({ onFileSelect, accept = ".yaml,.yml,.json", isUploading = false }: FileUploadProps) {
  const [isDragging, setIsDragging] = useState(false)

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(true)
  }, [])

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
  }, [])

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setIsDragging(false)
      const file = e.dataTransfer.files[0]
      if (file) onFileSelect(file)
    },
    [onFileSelect]
  )

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0]
      if (file) onFileSelect(file)
    },
    [onFileSelect]
  )

  return (
    <div
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      className={cn(
        "flex flex-col items-center justify-center rounded-xl border-2 border-dashed p-12 transition-colors",
        isDragging
          ? "border-chart-1 bg-chart-1/5"
          : "border-border hover:border-muted-foreground/50",
        isUploading && "pointer-events-none opacity-60"
      )}
    >
      <div className="mb-4 rounded-full bg-muted p-4">
        {isUploading ? (
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-muted-foreground border-t-chart-1" />
        ) : (
          <Upload className="h-8 w-8 text-muted-foreground" />
        )}
      </div>
      <p className="mb-1 text-sm font-medium">
        {isUploading ? "Uploading..." : "Drag & drop your OpenAPI file"}
      </p>
      <p className="mb-4 text-xs text-muted-foreground">
        Supports YAML and JSON formats
      </p>
      <label className="cursor-pointer rounded-lg bg-secondary px-4 py-2 text-sm font-medium transition-colors hover:bg-secondary/80">
        <span className="flex items-center gap-2">
          <FileText className="h-4 w-4" />
          Browse Files
        </span>
        <input
          type="file"
          accept={accept}
          onChange={handleChange}
          className="hidden"
        />
      </label>
    </div>
  )
}
