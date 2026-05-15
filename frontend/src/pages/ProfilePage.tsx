/**
 * Analysis / Profile page.
 * Datasets displayed as collapsible accordion rows (collapsed by default).
 * Score shown inline in the page header — no separate ScoreHero block.
 * Navigation to next steps via a minimal text-link row.
 */
import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { DatasetResult, Grade, ProposalsSummary } from "../api/client";
import IssueList from "../components/IssueList";
import ColumnStatsTable from "../components/ColumnStatsTable";
import NavBar from "../components/NavBar";
import WorkflowProgress from "../components/WorkflowProgress";

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

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

const GRADE_DOT: Record<Grade, string> = {
  Green: "bg-green-500",
  Amber: "bg-amber-400",
  Red:   "bg-red-500",
};

// ── Dataset accordion row ──────────────────────────────────────────────────

type ActiveTab = "issues" | "columns";

function DatasetRow({ dataset }: { dataset: DatasetResult }) {
  const [open,    setOpen]    = useState(false);
  const [tab,     setTab]     = useState<ActiveTab>("issues");
  const { profile, score, original_filename, size_bytes } = dataset;
  const issueCount = score.penalties.length;

  return (
    <div className={`overflow-hidden rounded-xl border transition-colors ${open ? "border-slate-700 bg-slate-900" : "border-slate-800 bg-slate-900/60 hover:border-slate-700"}`}>
      {/* Collapsed row */}
      <button
        className="w-full flex items-center gap-4 px-5 py-3.5 text-left"
        onClick={() => setOpen((v) => !v)}
      >
        <span className={`h-2 w-2 shrink-0 rounded-full ${GRADE_DOT[score.grade]}`} />

        <span className="flex-1 min-w-0">
          <span className="text-sm font-medium text-slate-200 truncate">{original_filename}</span>
          <span className="ml-3 text-xs text-slate-600">
            {profile.row_count.toLocaleString()} rows · {profile.column_count} cols · {formatBytes(size_bytes)}
            {profile.duplicate_row_count > 0 && (
              <span className="ml-2 text-amber-600">{profile.duplicate_row_count} dupes</span>
            )}
          </span>
        </span>

        <div className="flex items-center gap-3 shrink-0">
          {issueCount > 0 && (
            <span className="rounded-full bg-amber-950/60 px-2 py-0.5 text-xs text-amber-400 border border-amber-900/50">
              {issueCount} issue{issueCount !== 1 ? "s" : ""}
            </span>
          )}
          <span className={`text-lg font-black ${GRADE_COLOUR[score.grade]}`}>
            {Math.round(score.score)}
          </span>
          <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${GRADE_BADGE[score.grade]}`}>
            {score.grade}
          </span>
          <svg
            className={`h-3.5 w-3.5 text-slate-600 transition-transform ${open ? "rotate-180" : ""}`}
            fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
          </svg>
        </div>
      </button>

      {/* Expanded detail */}
      {open && (
        <div className="border-t border-slate-800">
          {/* Critical field pills */}
          {score.critical_field_issues.length > 0 && (
            <div className="flex flex-wrap gap-2 px-5 pt-3">
              {score.critical_field_issues.map((ci) => (
                <span
                  key={ci.field}
                  className="inline-flex items-center gap-1.5 rounded-full border border-red-900 bg-red-950/40 px-2.5 py-0.5 text-xs font-medium text-red-300"
                >
                  <span className="h-1.5 w-1.5 rounded-full bg-red-400 shrink-0" />
                  {ci.field}: {ci.null_count} missing
                </span>
              ))}
            </div>
          )}

          {/* Tabs */}
          <div className="flex border-b border-slate-800 mt-2">
            {(["issues", "columns"] as ActiveTab[]).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={[
                  "px-5 py-2.5 text-xs font-medium transition-colors",
                  tab === t
                    ? "border-b-2 border-blue-500 text-blue-400"
                    : "text-slate-500 hover:text-slate-300",
                ].join(" ")}
              >
                {t === "issues"
                  ? `Issues (${issueCount})`
                  : `Columns (${profile.column_count})`}
              </button>
            ))}
          </div>

          <div className="p-5">
            {tab === "issues"  && <IssueList penalties={score.penalties} />}
            {tab === "columns" && <ColumnStatsTable columns={profile.columns} />}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────

interface LocationState {
  session_id:        string;
  datasets:          DatasetResult[];
  proposals_summary: ProposalsSummary;
}

export default function ProfilePage() {
  const location = useLocation();
  const navigate  = useNavigate();
  const state     = location.state as LocationState | null;

  if (!state?.datasets?.length) {
    navigate("/", { replace: true });
    return null;
  }

  const { datasets, session_id, proposals_summary } = state;
  const avgScore   = datasets.reduce((s, d) => s + d.score.score, 0) / datasets.length;
  const avgGrade: Grade = avgScore >= 75 ? "Green" : avgScore >= 50 ? "Amber" : "Red";
  const totalIssues = datasets.reduce((n, d) => n + d.score.penalties.length, 0);

  return (
    <div className="min-h-screen bg-slate-950">
      <NavBar sessionId={session_id} />

      <main className="mx-auto max-w-5xl px-6 py-10 space-y-8">

        <WorkflowProgress current="analyse" />

        {/* Page header — score inline */}
        <div className="flex items-start justify-between gap-6">
          <div>
            <h1 className="text-xl font-semibold text-white">Analysis</h1>
            <div className="mt-1.5 flex flex-wrap items-center gap-3 text-xs text-slate-500">
              <span className="font-mono">{session_id.slice(0, 8)}</span>
              <span>{datasets.length} dataset{datasets.length !== 1 ? "s" : ""}</span>
              {totalIssues > 0 && <span className="text-amber-500">{totalIssues} issue{totalIssues !== 1 ? "s" : ""}</span>}
              {proposals_summary?.total > 0 && (
                <span className="text-green-500">{proposals_summary.total} proposal{proposals_summary.total !== 1 ? "s" : ""}</span>
              )}
            </div>
          </div>
          <div className="text-right shrink-0">
            <div className={`text-4xl font-black leading-none ${GRADE_COLOUR[avgGrade]}`}>
              {Math.round(avgScore)}
            </div>
            <span className={`mt-1 inline-block rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${GRADE_BADGE[avgGrade]}`}>
              {avgGrade}
            </span>
            <p className="mt-0.5 text-[10px] text-slate-600 uppercase tracking-wider">Data health</p>
          </div>
        </div>

        {/* Dataset accordion rows */}
        <div className="space-y-2">
          {datasets.map((ds) => (
            <DatasetRow key={ds.saved_as} dataset={ds} />
          ))}
        </div>

        {/* Minimal next-step links */}
        <div className="flex flex-wrap items-center gap-1 border-t border-slate-800/60 pt-5">
          <span className="text-xs text-slate-600 mr-2">Next:</span>
          {proposals_summary?.total > 0 && (
            <button
              onClick={() => navigate(`/proposals/${session_id}`)}
              className="rounded-lg px-3 py-1.5 text-xs font-medium text-slate-400 hover:bg-slate-800 hover:text-white transition-colors"
            >
              Review proposals
              <span className="ml-1.5 text-slate-600">({proposals_summary.total})</span>
            </button>
          )}
          <button
            onClick={() => navigate(`/sessions/${session_id}/joins`)}
            className="rounded-lg px-3 py-1.5 text-xs font-medium text-slate-400 hover:bg-slate-800 hover:text-white transition-colors"
          >
            Explore joins
          </button>
          <button
            onClick={() => navigate(`/sessions/${session_id}/dashboard`)}
            className="rounded-lg px-3 py-1.5 text-xs font-medium text-slate-400 hover:bg-slate-800 hover:text-white transition-colors"
          >
            Dashboard
          </button>
        </div>

      </main>
    </div>
  );
}
