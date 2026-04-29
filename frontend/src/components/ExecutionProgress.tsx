import type { ExecutionStatus } from "@/types"
import { cn } from "@/lib/utils"
import { CheckCircle2, XCircle, Clock, Loader2, Ban } from "lucide-react"

const statusConfig: Record<ExecutionStatus, { label: string; color: string; icon: React.ComponentType<{ className?: string }> }> = {
  pending: { label: "Pending", color: "text-muted-foreground", icon: Clock },
  running: { label: "Running", color: "text-chart-1", icon: Loader2 },
  completed: { label: "Completed", color: "text-emerald-400", icon: CheckCircle2 },
  failed: { label: "Failed", color: "text-red-400", icon: XCircle },
  cancelled: { label: "Cancelled", color: "text-amber-400", icon: Ban },
}

interface ExecutionProgressProps {
  status: ExecutionStatus
  progress: number
  total: number
}

export default function ExecutionProgress({ status, progress, total }: ExecutionProgressProps) {
  const config = statusConfig[status]
  const Icon = config.icon
  const percentage = total > 0 ? Math.round((progress / total) * 100) : 0

  return (
    <div className="rounded-xl border border-border p-6">
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Icon className={cn("h-5 w-5", config.color, status === "running" && "animate-spin")} />
          <span className={cn("text-sm font-medium", config.color)}>{config.label}</span>
        </div>
        <span className="text-sm text-muted-foreground">
          {progress} / {total} ({percentage}%)
        </span>
      </div>

      {/* Progress Bar */}
      <div className="h-2 overflow-hidden rounded-full bg-muted">
        <div
          className="h-full rounded-full bg-chart-1 transition-all duration-500"
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  )
}
