import { useState } from "react"
import { api } from "@/services/api"
import type { ApiEndpoint, ParseResponse } from "@/types"
import FileUpload from "@/components/FileUpload"
import EndpointTable from "@/components/EndpointTable"

export default function SchemaPage() {
  const [isUploading, setIsUploading] = useState(false)
  const [isParsing, setIsParsing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [parsedSchema, setParsedSchema] = useState<ParseResponse | null>(null)
  const [endpoints, setEndpoints] = useState<ApiEndpoint[]>([])

  const handleFileSelect = async (file: File) => {
    setIsUploading(true)
    setError(null)
    try {
      const result = await api.schema.upload(file)
      // Auto-parse after upload
      setIsParsing(true)
      const parsed = await api.schema.parse(result.schema_id)
      setParsedSchema(parsed)
      setEndpoints(parsed.endpoints)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed")
    } finally {
      setIsUploading(false)
      setIsParsing(false)
    }
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Schema</h1>
        <p className="text-sm text-muted-foreground">
          Upload and parse OpenAPI specification files
        </p>
      </div>

      {/* Upload Area */}
      <FileUpload onFileSelect={handleFileSelect} isUploading={isUploading} />

      {error && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-400">
          {error}
        </div>
      )}

      {isParsing && (
        <div className="rounded-xl border border-border p-4 text-center text-sm text-muted-foreground">
          <div className="mx-auto mb-2 h-5 w-5 animate-spin rounded-full border-2 border-muted-foreground border-t-chart-1" />
          Parsing schema...
        </div>
      )}

      {/* Schema Info */}
      {parsedSchema && (
        <div className="rounded-xl border border-border p-6">
          <h2 className="mb-3 text-lg font-semibold">Schema Details</h2>
          <div className="grid grid-cols-3 gap-4 text-sm">
            <div>
              <p className="text-muted-foreground">Schema ID</p>
              <p className="font-mono text-xs">{parsedSchema.schema_id}</p>
            </div>
            <div>
              <p className="text-muted-foreground">Title</p>
              <p>{parsedSchema.title || "-"}</p>
            </div>
            <div>
              <p className="text-muted-foreground">Version</p>
              <p>{parsedSchema.version || "-"}</p>
            </div>
          </div>
        </div>
      )}

      {/* Endpoints Table */}
      {endpoints.length > 0 && (
        <div>
          <h2 className="mb-3 text-lg font-semibold">
            Endpoints ({endpoints.length})
          </h2>
          <EndpointTable endpoints={endpoints} />
        </div>
      )}
    </div>
  )
}
