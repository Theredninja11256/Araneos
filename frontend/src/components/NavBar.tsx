/**
 * NavBar — dark mode persistent navigation.
 * Brand: Araneos
 */
import { useLocation, useNavigate } from "react-router-dom";

interface NavBarProps {
  sessionId?: string;
}

export default function NavBar({ sessionId: propSessionId }: NavBarProps = {}) {
  const location = useLocation();
  const navigate  = useNavigate();

  const urlSessionId =
    location.pathname.match(/\/proposals\/([^/]+)/)?.[1] ||
    location.pathname.match(/\/sessions\/([^/]+)/)?.[1];

  const sessionId = propSessionId ?? urlSessionId;

  const p = location.pathname;
  const isUpload    = p === "/";
  const isAnalysis  = p === "/results";
  const isProposals = p.startsWith("/proposals/");
  const isJoins     = p.includes("/joins");
  const isDashboard = p.includes("/dashboard");

  function linkCls(active: boolean, disabled = false): string {
    const base = "text-sm px-3 py-1.5 rounded-md transition-colors";
    if (active)   return `${base} text-white font-semibold`;
    if (disabled) return `${base} text-slate-600 cursor-not-allowed`;
    return `${base} text-slate-400 hover:text-slate-100 font-medium`;
  }

  return (
    <header className="sticky top-0 z-30 border-b border-slate-800 bg-slate-950">
      <div className="mx-auto flex h-13 max-w-7xl items-center justify-between px-6 py-3">

        {/* Brand */}
        <button
          onClick={() => navigate("/")}
          className="flex items-center gap-2.5 focus:outline-none"
        >
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-blue-600">
            <svg className="h-4 w-4 text-white" fill="none" viewBox="0 0 24 24" strokeWidth={1.8} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 3c-1.2 5.4-5.4 9-9 9 0 5.4 4.2 9.6 9 9.9 4.8-.3 9-4.5 9-9.9-3.6 0-7.8-3.6-9-9z" />
            </svg>
          </div>
          <span className="text-sm font-semibold tracking-tight text-white">Araneos</span>
        </button>

        {/* Nav */}
        <nav className="hidden items-center gap-0.5 sm:flex">
          {[
            { label: "Upload",   active: isUpload,    onClick: () => navigate("/"),                                         disabled: false },
            { label: "Analysis", active: isAnalysis,  onClick: () => navigate("/results"),                                  disabled: false },
            { label: "Review",   active: isProposals, onClick: () => sessionId && navigate(`/proposals/${sessionId}`),       disabled: !sessionId },
            { label: "Joins",    active: isJoins,     onClick: () => sessionId && navigate(`/sessions/${sessionId}/joins`),  disabled: !sessionId },
            { label: "Dashboard",active: isDashboard, onClick: () => sessionId && navigate(`/sessions/${sessionId}/dashboard`), disabled: !sessionId },
          ].map(({ label, active, onClick, disabled }) => (
            <button
              key={label}
              onClick={onClick}
              disabled={disabled}
              className={linkCls(active, disabled)}
            >
              {label}
            </button>
          ))}
        </nav>

        <span className="text-xs text-slate-500 sm:hidden">
          {isUpload ? "Upload" : isAnalysis ? "Analysis" : isProposals ? "Review" : isJoins ? "Joins" : isDashboard ? "Dashboard" : ""}
        </span>
      </div>
    </header>
  );
}
