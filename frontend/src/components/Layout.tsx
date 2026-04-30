import { NavLink, Outlet } from "react-router-dom"
import {
  LayoutDashboard,
  FileCode2,
  FlaskConical,
  Play,
  FileBarChart,
  Zap,
  Network,
  Puzzle,
  GitBranch,
  Users,
  BarChart3,
  CreditCard,
} from "lucide-react"
import { cn } from "@/lib/utils"

const navItems = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/schema", label: "Schema", icon: FileCode2 },
  { to: "/scenarios", label: "Scenarios", icon: FlaskConical },
  { to: "/execution", label: "Execution", icon: Play },
  { to: "/reports", label: "Reports", icon: FileBarChart },
]

const proNavItems = [
  { to: "/distributed", label: "Distributed", icon: Network },
  { to: "/plugins", label: "Plugins", icon: Puzzle },
  { to: "/cicd", label: "CI/CD", icon: GitBranch },
  { to: "/team", label: "Team", icon: Users },
  { to: "/analytics", label: "Analytics", icon: BarChart3 },
  { to: "/pricing", label: "Pricing", icon: CreditCard },
]

export default function Layout() {
  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar */}
      <aside className="flex w-64 flex-col border-r border-border bg-sidebar-background">
        {/* Logo */}
        <div className="flex h-16 items-center gap-2 border-b border-border px-6">
          <Zap className="h-6 w-6 text-chart-1" />
          <span className="text-lg font-bold tracking-tight">API Chaos Agent</span>
        </div>

        {/* Navigation */}
        <nav className="flex-1 space-y-1 px-3 py-4">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
                  isActive
                    ? "bg-sidebar-accent text-sidebar-accent-foreground"
                    : "text-muted-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
                )
              }
            >
              <item.icon className="h-4 w-4" />
              {item.label}
            </NavLink>
          ))}

          <div className="pt-4 pb-2">
            <p className="px-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Pro
            </p>
          </div>
          {proNavItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
                  isActive
                    ? "bg-sidebar-accent text-sidebar-accent-foreground"
                    : "text-muted-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
                )
              }
            >
              <item.icon className="h-4 w-4" />
              {item.label}
            </NavLink>
          ))}
        </nav>

        {/* Footer */}
        <div className="border-t border-border p-4">
          <p className="text-xs text-muted-foreground">v2.0.0</p>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-7xl p-8">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
