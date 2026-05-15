/**
 * CTO / Executive Dashboard — Stage 8.
 * Compact header strip (score + RAG + alert count) → two-column detail.
 * No standalone ScoreCard, RAGSummary, or QualityContext blocks.
 */

import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  getCTODashboard,
  downloadDashboardReport,
  type CTODashboard,
  type CriticalAlert,
  type JoinOpportunity,
  type Grade,
} from "../api/client";
import NavBar from "../components/NavBar";
import WorkflowProgress from "../components/WorkflowProgress";

// ── Grade helpers ─────────────────────────────────────────────────────────

const GRADE_COLOUR: Record<Grade, string> = {
  Green: "text-green-400",
  Amber: "text-amber-400",
  Red:   "text-red-400",
};

const GRADE_BADGE: Record<Grade, string> = {
  Green: "bg-green-950/70 text-green-300",
  Amber: "bg-amber-950/70 text-amber-300",
  Red:   "bg-red-950/70   text-red-300",
};

const SEVERITY_BORDER: Record<string, string> = {
  critical: "border-red-900   bg-red-950/30",
  high:     "border-orange-900 bg-orange-950/30",
  medium:   "border-amber-900  bg-amber-950/30",
  low:      "border-slate-800  bg-slate-800/30",
};

const SEVERITY_DOT: Record<string, string> = {
  critical: "bg-red-500",
  high:     "bg-orange-500",
  medium:   "bg-amber-400",
  low:      "bg-slate-500",
};

const SEVERITY_LABEL: Record<string, string> = {
  critical: "text-red-300    bg-red-950",
  high:     "text-orange-300 bg-orange-950",
  medium:   "text-amber-300  bg-amber-950",
  low:      "text-slate-400  bg-slate-800",
};

// ── Alerts column ─────────────────────────────────────────────────────────

function AlertsColumn({ alerts }: { alerts: CriticalAlert[] }) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-widest text-slate-600 mb-3">
        Critical Alerts
      </p>
      {alerts.length === 0 ? (
        <div className="flex items-center gap-2 rounded-xl border border-slate-800 px-4 py-3">
          <span className="h-2 w-2 rounded-full bg-green-500" />
          <p className="text-sm text-slate-500">No critical issues</p>
        </div>
      ) : (
        <div className="space-y-2">
          {alerts.map((alert, i) => {
            const border   = SEVERITY_BORDER[alert.severity] ?? SEVERITY_BORDER.low;
            const dot      = SEVERITY_DOT[alert.severity]   ?? SEVERITY_DOT.low;
            const labelCls = SEVERITY_LABEL[alert.severity] ?? SEVERITY_LABEL.low;
            return (
              <div key={i} className={`rounded-xl border-l-4 px-4 py-3 ${border}`}>
                <div className="flex items-start gap-2">
                  <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${dot}`} />
                  <p className="text-sm text-slate-300 leading-relaxed">{alert.alert_text}</p>
                </div>
                <div className="mt-1.5 flex items-center gap-2 pl-4">
                  <span className="font-mono text-[11px] text-slate-500">{alert.dataset}</span>
                  {alert.column && (
                    <span className="font-mono text-[11px] text-slate-600">{alert.column}</span>
                  )}
                  <span className={`ml-auto rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${labelCls}`}>
                    {alert.severity}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── Join opportunities column ─────────────────────────────────────────────

function JoinsColumn({ opportunities }: { opportunities: JoinOpportunity[] }) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-widest text-slate-600 mb-3">
        Join Opportunities
      </p>
      {opportunities.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-800 px-4 py-6 text-center">
          <p className="text-sm text-slate-600">Upload related datasets to unlock insights.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {opportunities.map((opp, i) => (
            <div key={i} className="rounded-xl border border-slate-800 bg-slate-900/60 px-4 py-3">
              <div className="flex items-start justify-between gap-3">
                <p className="text-sm font-medium text-slate-200 leading-snug flex-1 min-w-0">
                  {opp.business_summary}
                </p>
                <span className="shrink-0 rounded-lg bg-blue-950 px-2 py-1 text-xs font-bold text-blue-300">
                  {opp.match_rate}%
                </span>
              </div>
              <div className="mt-1.5 flex items-center gap-2">
                <code className="rounded bg-slate-800 border border-slate-700 px-1 py-0.5 text-[11px] text-slate-500">
                  {opp.join_key}
                </code>
                <span className="text-[11px] text-slate-600">·</span>
                <span className="text-[11px] text-slate-600">{opp.insights_count} insight{opp.insights_count !== 1 ? "s" : ""}</span>
              </div>
              {opp.top_insights.length > 0 && (
                <ul className="mt-1.5 space-y-0.5 pl-0.5">
                  {opp.top_insights.slice(0, 2).map((ins, j) => (
                    <li key={j} className="text-xs text-slate-600 flex items-center gap-1">
                      <span className="text-blue-700">›</span> {ins}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────

export default function CTODashboardPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate      = useNavigate();

  const [dashboard, setDashboard] = useState<CTODashboard | null>(null);
  const [loading,   setLoading]   = useState(true);
  const [error,     setError]     = useState<string | null>(null);

  useEffect(() => {
    if (!sessionId) { setError("No session ID."); setLoading(false); return; }
    getCTODashboard(sessionId)
      .then(setDashboard)
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [sessionId]);

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-950">
        <NavBar />
        <div className="flex min-h-[70vh] flex-col items-center justify-center gap-3">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-slate-800 border-t-blue-500" />
          <p className="text-sm text-slate-500">Building dashboard…</p>
        </div>
      </div>
    );
  }

  if (error || !dashboard) {
    return (
      <div className="min-h-screen bg-slate-950">
        <NavBar />
        <div className="mx-auto mt-20 max-w-md rounded-2xl border border-red-900 bg-red-950/30 p-8 text-center">
          <p className="text-base font-semibold text-red-300 mb-2">Dashboard unavailable</p>
          <p className="text-sm text-red-400/80 mb-5">{error ?? "Unknown error."}</p>
          <button
            onClick={() => navigate("/")}
            className="rounded-xl bg-red-800 px-5 py-2 text-sm font-semibold text-white hover:bg-red-700 transition-colors"
          >
            Back to upload
          </button>
        </div>
      </div>
    );
  }

  const { overall_score, grade, rag_summary, critical_alerts, join_opportunities, dataset_count } = dashboard;
  const ts = new Date(dashboard.generated_at).toLocaleString("en-GB", {
    day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
  });

  return (
    <div className="min-h-screen bg-slate-950">
      <NavBar />

      <main className="mx-auto max-w-5xl px-6 py-10 space-y-8">

        <WorkflowProgress current="dashboard" />

        {/* ── Header: score + RAG inline + export ── */}
        <div className="flex items-start justify-between gap-6">
          <div>
            <h1 className="text-xl font-semibold text-white">Dashboard</h1>
            <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-500">
              <span className="font-mono">{sessionId?.slice(0, 8)}</span>
              <span>{dataset_count} dataset{dataset_count !== 1 ? "s" : ""}</span>
              <span>{ts}</span>
            </div>
          </div>
          <button
            onClick={() => sessionId && downloadDashboardReport(sessionId)}
            className="shrink-0 flex items-center gap-1.5 rounded-lg border border-slate-700 bg-transparent px-3 py-1.5 text-xs font-medium text-slate-400 hover:border-slate-600 hover:text-slate-200 transition-colors"
          >
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
            </svg>
            Export report
          </button>
        </div>

        {/* ── Top metrics strip ── */}
        <div className="flex flex-wrap items-center gap-6 rounded-2xl border border-slate-800 bg-slate-900 px-6 py-5">
          {/* Score */}
          <div className="flex items-end gap-2">
            <span className={`text-5xl font-black leading-none ${GRADE_COLOUR[grade]}`}>
              {Math.round(overall_score)}
            </span>
            <div className="mb-0.5">
              <span className={`block rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${GRADE_BADGE[grade]}`}>
                {grade}
              </span>
              <p className="mt-0.5 text-[10px] uppercase tracking-widest text-slate-600">Data health</p>
            </div>
          </div>

          <div className="hidden h-8 w-px bg-slate-800 sm:block" />

          {/* RAG */}
          <div className="flex items-center gap-4 text-sm">
            <span>
              <strong className="text-green-400">{rag_summary.green}</strong>
              <span className="ml-1 text-slate-600 text-xs">green</span>
            </span>
            <span>
              <strong className="text-amber-400">{rag_summary.amber}</strong>
              <span className="ml-1 text-slate-600 text-xs">amber</span>
            </span>
            <span>
              <strong className="text-red-400">{rag_summary.red}</strong>
              <span className="ml-1 text-slate-600 text-xs">red</span>
            </span>
          </div>

          <div className="hidden h-8 w-px bg-slate-800 sm:block" />

          {/* Alert count */}
          <div className="flex items-center gap-2">
            <span className={`text-xl font-black ${critical_alerts.length > 0 ? "text-red-400" : "text-slate-600"}`}>
              {critical_alerts.length}
            </span>
            <span className="text-xs text-slate-600">alert{critical_alerts.length !== 1 ? "s" : ""}</span>
          </div>
        </div>

        {/* ── Two-column detail ── */}
        <div className="grid grid-cols-1 gap-8 lg:grid-cols-2">
          <AlertsColumn alerts={critical_alerts} />
          <JoinsColumn  opportunities={join_opportunities} />
        </div>

      </main>
    </div>
  );
}
