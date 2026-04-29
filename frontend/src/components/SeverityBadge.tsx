import type { Severity } from "@/types"
import { cn } from "@/lib/utils"

const severityConfig: Record<Severity, { label: string; color: string; dot: string }> = {
  critical: { label: "Critical", color: "bg-red-500/15 text-red-400", dot: "bg-red-500" },
  high: { label: "High", color: "bg-orange-500/15 text-orange-400", dot: "bg-orange-500" },
  medium: { label: "Medium", color: "bg-yellow-500/15 text-yellow-400", dot: "bg-yellow-500" },
  low: { label: "Low", color: "bg-blue-500/15 text-blue-400", dot: "bg-blue-500" },
  info: { label: "Info", color: "bg-emerald-500/15 text-emerald-400", dot: "bg-emerald-500" },
}

interface SeverityBadgeProps {
  severity: Severity
  size?: "sm" | "md"
}

export default function SeverityBadge({ severity, size = "sm" }: SeverityBadgeProps) {
  const config = severityConfig[severity]
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md font-medium",
        config.color,
        size === "sm" ? "px-2 py-0.5 text-xs" : "px-2.5 py-1 text-sm"
      )}
    >
      <span className={cn("h-1.5 w-1.5 rounded-full", config.dot)} />
      {config.label}
    </span>
  )
}
