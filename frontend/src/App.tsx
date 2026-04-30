import { BrowserRouter, Routes, Route } from "react-router-dom"
import Layout from "@/components/Layout"
import DashboardPage from "@/pages/DashboardPage"
import SchemaPage from "@/pages/SchemaPage"
import ScenariosPage from "@/pages/ScenariosPage"
import ExecutionPage from "@/pages/ExecutionPage"
import ReportsPage from "@/pages/ReportsPage"
import DistributedPage from "@/pages/DistributedPage"
import PluginsPage from "@/pages/PluginsPage"
import CiCdPage from "@/pages/CiCdPage"
import TeamPage from "@/pages/TeamPage"
import AnalyticsPage from "@/pages/AnalyticsPage"
import PricingPage from "@/pages/PricingPage"

export default function App() {
  return (
    <BrowserRouter>
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
    </BrowserRouter>
  )
}
