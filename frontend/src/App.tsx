import { BrowserRouter, Routes, Route } from "react-router-dom"
import Layout from "@/components/Layout"
import DashboardPage from "@/pages/DashboardPage"
import SchemaPage from "@/pages/SchemaPage"
import ScenariosPage from "@/pages/ScenariosPage"
import ExecutionPage from "@/pages/ExecutionPage"
import ReportsPage from "@/pages/ReportsPage"

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
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
