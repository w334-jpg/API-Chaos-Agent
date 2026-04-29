import type { ApiEndpoint } from "@/types"
import { cn } from "@/lib/utils"

const methodColors: Record<string, string> = {
  GET: "bg-emerald-500/15 text-emerald-400",
  POST: "bg-blue-500/15 text-blue-400",
  PUT: "bg-amber-500/15 text-amber-400",
  PATCH: "bg-orange-500/15 text-orange-400",
  DELETE: "bg-red-500/15 text-red-400",
  HEAD: "bg-purple-500/15 text-purple-400",
  OPTIONS: "bg-gray-500/15 text-gray-400",
}

interface EndpointTableProps {
  endpoints: ApiEndpoint[]
  onSelect?: (endpoint: ApiEndpoint) => void
}

export default function EndpointTable({ endpoints, onSelect }: EndpointTableProps) {
  if (endpoints.length === 0) {
    return (
      <div className="rounded-xl border border-border p-8 text-center">
        <p className="text-sm text-muted-foreground">No endpoints found. Upload and parse a schema first.</p>
      </div>
    )
  }

  return (
    <div className="overflow-hidden rounded-xl border border-border">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border bg-muted/50">
            <th className="px-4 py-3 text-left font-medium text-muted-foreground">Method</th>
            <th className="px-4 py-3 text-left font-medium text-muted-foreground">Path</th>
            <th className="px-4 py-3 text-left font-medium text-muted-foreground">Summary</th>
            <th className="px-4 py-3 text-left font-medium text-muted-foreground">Params</th>
          </tr>
        </thead>
        <tbody>
          {endpoints.map((ep, i) => (
            <tr
              key={`${ep.method}-${ep.path}-${i}`}
              onClick={() => onSelect?.(ep)}
              className={cn(
                "border-b border-border transition-colors last:border-0",
                onSelect && "cursor-pointer hover:bg-muted/30"
              )}
            >
              <td className="px-4 py-3">
                <span className={cn("rounded-md px-2 py-0.5 text-xs font-bold", methodColors[ep.method] || "bg-muted text-muted-foreground")}>
                  {ep.method}
                </span>
              </td>
              <td className="px-4 py-3 font-mono text-xs">{ep.path}</td>
              <td className="px-4 py-3 text-muted-foreground">{ep.summary || "-"}</td>
              <td className="px-4 py-3 text-muted-foreground">{ep.parameters?.length ?? 0}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
