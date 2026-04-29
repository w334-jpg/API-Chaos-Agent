import { FileCode2, FlaskConical, Play, ShieldAlert } from "lucide-react"
import { Link } from "react-router-dom"

const stats = [
  {
    label: "Schemas",
    value: "0",
    icon: FileCode2,
    color: "text-blue-400",
    bg: "bg-blue-500/10",
    link: "/schema",
  },
  {
    label: "Scenarios",
    value: "0",
    icon: FlaskConical,
    color: "text-purple-400",
    bg: "bg-purple-500/10",
    link: "/scenarios",
  },
  {
    label: "Executions",
    value: "0",
    icon: Play,
    color: "text-emerald-400",
    bg: "bg-emerald-500/10",
    link: "/execution",
  },
  {
    label: "Vulnerabilities",
    value: "0",
    icon: ShieldAlert,
    color: "text-red-400",
    bg: "bg-red-500/10",
    link: "/reports",
  },
]

export default function DashboardPage() {
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-sm text-muted-foreground">
          Overview of your API chaos testing activity
        </p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {stats.map((stat) => (
          <Link
            key={stat.label}
            to={stat.link}
            className="rounded-xl border border-border p-6 transition-colors hover:border-muted-foreground/30"
          >
            <div className="flex items-center gap-3">
              <div className={`rounded-lg p-2.5 ${stat.bg}`}>
                <stat.icon className={`h-5 w-5 ${stat.color}`} />
              </div>
              <div>
                <p className="text-2xl font-bold">{stat.value}</p>
                <p className="text-xs text-muted-foreground">{stat.label}</p>
              </div>
            </div>
          </Link>
        ))}
      </div>

      {/* Quick Start */}
      <div className="rounded-xl border border-border p-8">
        <h2 className="mb-2 text-lg font-semibold">Quick Start</h2>
        <p className="mb-6 text-sm text-muted-foreground">
          Get started with API Chaos Agent in 3 steps
        </p>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <div className="rounded-lg bg-muted/50 p-4">
            <div className="mb-2 flex h-8 w-8 items-center justify-center rounded-full bg-chart-1 text-sm font-bold text-background">
              1
            </div>
            <h3 className="text-sm font-medium">Upload Schema</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              Upload your OpenAPI specification file to begin
            </p>
          </div>
          <div className="rounded-lg bg-muted/50 p-4">
            <div className="mb-2 flex h-8 w-8 items-center justify-center rounded-full bg-chart-1 text-sm font-bold text-background">
              2
            </div>
            <h3 className="text-sm font-medium">Generate Scenarios</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              Auto-generate chaos test scenarios for your endpoints
            </p>
          </div>
          <div className="rounded-lg bg-muted/50 p-4">
            <div className="mb-2 flex h-8 w-8 items-center justify-center rounded-full bg-chart-1 text-sm font-bold text-background">
              3
            </div>
            <h3 className="text-sm font-medium">Run & Report</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              Execute tests and review vulnerability reports
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
