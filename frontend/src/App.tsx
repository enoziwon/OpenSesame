import { useState } from "react";
import { Route, Routes, Navigate, useLocation } from "react-router-dom";
import { useEffect } from "react";
import { useAllergies } from "./hooks/useAllergies";
import type { Analysis } from "./types/analysis";
import LandingPage from "./pages/LandingPage";
import AllergiesPage from "./pages/AllergiesPage";
import ScanPage from "./pages/ScanPage";
import ResultsPage from "./pages/ResultsPage";
export default function App() {
  const profile = useAllergies();
  const [result, setResult] = useState<Analysis | null>(null);
  const location = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [location.pathname]);
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/allergies" element={<AllergiesPage {...profile} />} />
      <Route path="/scan" element={<ScanPage onResult={setResult} />} />
      <Route
        path="/results"
        element={<ResultsPage result={result} selected={profile.selected} />}
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
