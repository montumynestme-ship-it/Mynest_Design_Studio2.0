import { Navigate, Route, Routes } from 'react-router-dom';
import AppShell from './components/layout/AppShell';
import Dashboard from './pages/Dashboard';
import Projects from './pages/Projects';
import FloorPlans from './pages/FloorPlans';
import FloorPlanDetail from './pages/FloorPlanDetail';
import DesignStudio from './pages/DesignStudio';
import AIGenerations from './pages/AIGenerations';
import Settings from './pages/Settings';

function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/projects" element={<Projects />} />
        <Route path="/floor-plans" element={<FloorPlans />} />
        <Route path="/floor-plans/:id" element={<FloorPlanDetail />} />
        <Route path="/design-studio" element={<DesignStudio />} />
        <Route path="/ai-generations" element={<AIGenerations />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Route>
    </Routes>
  );
}

export default App;
