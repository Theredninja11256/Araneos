import { Routes, Route, Navigate } from "react-router-dom";
import UploadPage from "./pages/UploadPage";
import ProfilePage from "./pages/ProfilePage";
import ProposalsPage from "./pages/ProposalsPage";
import JoinIntelligencePage from "./pages/JoinIntelligencePage";
import CTODashboardPage from "./pages/CTODashboardPage";

/**
 * Root router.
 *
 * Stage 1: /                                  — Upload page
 * Stage 2: /results                           — Profiling + scoring results
 * Stage 3: /proposals/:sessionId              — Proposal review
 * Stage 7: /sessions/:sessionId/joins         — Join intelligence & insights
 * Stage 8: /sessions/:sessionId/dashboard     — CTO executive dashboard
 */
export default function App() {
  return (
    <Routes>
      <Route path="/" element={<UploadPage />} />
      <Route path="/results" element={<ProfilePage />} />
      <Route path="/proposals/:sessionId" element={<ProposalsPage />} />
      <Route path="/sessions/:sessionId/joins" element={<JoinIntelligencePage />} />
      <Route path="/sessions/:sessionId/dashboard" element={<CTODashboardPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
