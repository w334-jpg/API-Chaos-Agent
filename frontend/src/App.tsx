import { lazy, Suspense, Component, type ReactNode } from "react"
import { BrowserRouter, Routes, Route } from "react-router-dom"
import Layout from "@/components/Layout"

const DashboardPage = lazy(() => import("@/pages/DashboardPage"))
const SchemaPage = lazy(() => import("@/pages/SchemaPage"))
const ScenariosPage = lazy(() => import("@/pages/ScenariosPage"))
const ExecutionPage = lazy(() => import("@/pages/ExecutionPage"))
const ReportsPage = lazy(() => import("@/pages/ReportsPage"))
const DistributedPage = lazy(() => import("@/pages/DistributedPage"))
const PluginsPage = lazy(() => import("@/pages/PluginsPage"))
const CiCdPage = lazy(() => import("@/pages/CiCdPage"))
const TeamPage = lazy(() => import("@/pages/TeamPage"))
const AnalyticsPage = lazy(() => import("@/pages/AnalyticsPage"))
const PricingPage = lazy(() => import("@/pages/PricingPage"))

interface ErrorBoundaryState {
  hasError: boolean
  error: Error | null
}

class ErrorBoundary extends Component<{ children: ReactNode }, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false, error: null }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo): void {
    console.error("ErrorBoundary caught:", error, info)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: "2rem", textAlign: "center" }}>
          <h2 style={{ color: "#ef4444" }}>Something went wrong</h2>
          <p style={{ color: "#6b7280" }}>{this.state.error?.message}</p>
          <button
            onClick={() => this.setState({ hasError: false, error: null })}
            style={{
              marginTop: "1rem",
              padding: "0.5rem 1rem",
              background: "#3b82f6",
              color: "white",
              border: "none",
              borderRadius: "0.25rem",
              cursor: "pointer",
            }}
          >
            Try Again
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

function PageLoader() {
  return (
    <div style={{ display: "flex", justifyContent: "center", padding: "4rem" }}>
      <div style={{ color: "#6b7280" }}>Loading...</div>
    </div>
  )
}

export default function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <Suspense fallback={<PageLoader />}>
          <Routes>
            <Route element={<Layout />}>
              <Route path="/" element={<DashboardPage />} />
              <Route path="/schema" element={<SchemaPage />} />
              <Route path="/scenarios" element={<ScenariosPage />} />
              <Route path="/execution" element={<ExecutionPage />} />
              <Route path="/reports" element={<ReportsPage />} />
              <Route path="/distributed" element={<DistributedPage />} />
              <Route path="/plugins" element={<PluginsPage />} />
              <Route path="/cicd" element={<CiCdPage />} />
              <Route path="/team" element={<TeamPage />} />
              <Route path="/analytics" element={<AnalyticsPage />} />
              <Route path="/pricing" element={<PricingPage />} />
            </Route>
          </Routes>
        </Suspense>
      </BrowserRouter>
    </ErrorBoundary>
  )
}
