import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Shell from "./components/Shell";
import Landing from "./pages/Landing";
import AnalysisSetup from "./pages/AnalysisSetup";
import Processing from "./pages/Processing";
import Results from "./pages/Results";
import TargetDetail from "./pages/TargetDetail";
import WhyTarget from "./pages/WhyTarget";
import Contradictions from "./pages/Contradictions";
import ResearchGaps from "./pages/ResearchGaps";
import EvidenceNetwork from "./pages/EvidenceNetwork";
import Comparison from "./pages/Comparison";
import Report from "./pages/Report";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route element={<Shell />}>
          <Route path="/setup" element={<AnalysisSetup />} />
          <Route path="/processing" element={<Processing />} />
          <Route path="/results" element={<Results />} />
          <Route path="/target/:id" element={<TargetDetail />} />
          <Route path="/why/:id" element={<WhyTarget />} />
          <Route path="/contradictions/:id" element={<Contradictions />} />
          <Route path="/gaps/:id" element={<ResearchGaps />} />
          <Route path="/network/:id" element={<EvidenceNetwork />} />
          <Route path="/comparison" element={<Comparison />} />
          <Route path="/report/:id" element={<Report />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
