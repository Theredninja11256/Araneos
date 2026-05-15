import { useState } from "react";
import { useNavigate } from "react-router-dom";
import FileDropZone from "../components/FileDropZone";
import NavBar from "../components/NavBar";
import WorkflowProgress from "../components/WorkflowProgress";
import { uploadDatasets, AnalystRules, DEFAULT_ANALYST_RULES } from "../api/client";

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function FileItem({ file, onRemove }: { file: File; onRemove: () => void }) {
  const ext = file.name.split(".").pop()?.toUpperCase() ?? "FILE";
  return (
    <div className="flex items-center justify-between rounded-xl border border-slate-700 bg-slate-800/50 px-4 py-3">
      <div className="flex items-center gap-3">
        <span className="rounded-md bg-slate-700 px-1.5 py-0.5 text-[10px] font-semibold text-slate-300">
          {ext}
        </span>
        <div>
          <p className="text-sm font-medium text-slate-200 leading-tight">{file.name}</p>
          <p className="text-xs text-slate-500">{formatBytes(file.size)}</p>
        </div>
      </div>
      <button
        onClick={onRemove}
        className="ml-4 rounded-lg p-1.5 text-slate-500 hover:bg-slate-700 hover:text-slate-300 transition-colors"
        aria-label={`Remove ${file.name}`}
      >
        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>
  );
}

function RulesForm({
  rules,
  onChange,
}: {
  rules: AnalystRules;
  onChange: (r: AnalystRules) => void;
}) {
  const [open, setOpen] = useState(false);

  function update(key: keyof AnalystRules, raw: string) {
    const numeric = parseFloat(raw);
    const val = raw === "" ? null : isNaN(numeric) ? null : numeric;
    onChange({ ...rules, [key]: key === "date_format_standard" || key === "currency_symbol" ? raw : val });
  }

  return (
    <div className="mt-5 rounded-xl border border-slate-700 bg-slate-800/40">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between px-4 py-3 text-left text-sm text-slate-300 hover:text-white transition-colors"
      >
        <span className="font-medium">Analysis rules</span>
        <svg
          className={`h-4 w-4 text-slate-500 transition-transform ${open ? "rotate-180" : ""}`}
          fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {open && (
        <div className="border-t border-slate-700 px-4 pb-4 pt-3 grid grid-cols-2 gap-x-6 gap-y-4">
          <label className="block">
            <span className="text-xs text-slate-400">Min premium ({rules.currency_symbol})</span>
            <input
              type="number" step="0.01" placeholder="50"
              defaultValue={rules.min_premium ?? ""}
              onChange={(e) => update("min_premium", e.target.value)}
              className="mt-1 w-full rounded-lg bg-slate-900 border border-slate-700 px-3 py-1.5 text-sm text-white placeholder-slate-600 focus:border-blue-500 focus:outline-none"
            />
          </label>

          <label className="block">
            <span className="text-xs text-slate-400">Max premium ({rules.currency_symbol})</span>
            <input
              type="number" step="0.01" placeholder="No limit"
              defaultValue={rules.max_premium ?? ""}
              onChange={(e) => update("max_premium", e.target.value)}
              className="mt-1 w-full rounded-lg bg-slate-900 border border-slate-700 px-3 py-1.5 text-sm text-white placeholder-slate-600 focus:border-blue-500 focus:outline-none"
            />
          </label>

          <label className="block">
            <span className="text-xs text-slate-400">Max NCD (years)</span>
            <input
              type="number" step="1" placeholder="No limit"
              defaultValue={rules.max_ncd ?? ""}
              onChange={(e) => update("max_ncd", e.target.value)}
              className="mt-1 w-full rounded-lg bg-slate-900 border border-slate-700 px-3 py-1.5 text-sm text-white placeholder-slate-600 focus:border-blue-500 focus:outline-none"
            />
          </label>

          <label className="block">
            <span className="text-xs text-slate-400">Currency symbol</span>
            <input
              type="text" maxLength={3} placeholder="£"
              defaultValue={rules.currency_symbol}
              onChange={(e) => onChange({ ...rules, currency_symbol: e.target.value || "£" })}
              className="mt-1 w-full rounded-lg bg-slate-900 border border-slate-700 px-3 py-1.5 text-sm text-white placeholder-slate-600 focus:border-blue-500 focus:outline-none"
            />
          </label>

          <label className="block col-span-2">
            <span className="text-xs text-slate-400">Date output format (strftime)</span>
            <input
              type="text" placeholder="%d-%m-%y"
              defaultValue={rules.date_format_standard}
              onChange={(e) => onChange({ ...rules, date_format_standard: e.target.value || "%d-%m-%y" })}
              className="mt-1 w-full rounded-lg bg-slate-900 border border-slate-700 px-3 py-1.5 text-sm font-mono text-white placeholder-slate-600 focus:border-blue-500 focus:outline-none"
            />
            <p className="mt-1 text-xs text-slate-600">Default %d-%m-%y = DD-MM-YY</p>
          </label>
        </div>
      )}
    </div>
  );
}

export default function UploadPage() {
  const navigate  = useNavigate();
  const [queue,     setQueue]     = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [errorMsg,  setErrorMsg]  = useState<string>("");
  const [rules,     setRules]     = useState<AnalystRules>({ ...DEFAULT_ANALYST_RULES });

  function addFiles(incoming: File[]) {
    setQueue((prev) => {
      const names = new Set(prev.map((f) => f.name));
      return [...prev, ...incoming.filter((f) => !names.has(f.name))];
    });
    setErrorMsg("");
  }

  async function handleUpload() {
    if (queue.length === 0) return;
    setUploading(true);
    setErrorMsg("");
    try {
      const res = await uploadDatasets(queue, rules);
      navigate("/results", {
        state: {
          session_id:        res.session_id,
          datasets:          res.datasets,
          proposals_summary: res.proposals_summary,
          analyst_rules:     rules,
        },
      });
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : "Upload failed.");
      setUploading(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-950">
      <NavBar />

      <main className="mx-auto max-w-5xl px-6 py-12">

        {/* Workflow */}
        <div className="mb-10">
          <WorkflowProgress current="upload" />
        </div>

        {/* Hero */}
        <div className="mb-10">
          <h1 className="text-3xl font-semibold text-white tracking-tight">
            Clean insurance data faster
          </h1>
          <p className="mt-2 text-slate-400">
            Upload datasets, review issues, approve fixes, export clean data.
          </p>
        </div>

        {/* Upload card */}
        <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
          <FileDropZone onFilesSelected={addFiles} disabled={uploading} />

          {/* Analysis rules (always visible below drop zone) */}
          <RulesForm rules={rules} onChange={setRules} />

          {queue.length > 0 && (
            <div className="mt-5 space-y-2">
              <p className="text-xs text-slate-500">{queue.length} file{queue.length !== 1 ? "s" : ""} queued</p>
              {queue.map((f, i) => (
                <FileItem key={`${f.name}-${i}`} file={f} onRemove={() => setQueue((p) => p.filter((_, j) => j !== i))} />
              ))}
            </div>
          )}

          {queue.length > 0 && (
            <div className="mt-5 flex items-center gap-4">
              <button
                onClick={handleUpload}
                disabled={uploading}
                className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-6 py-2.5 text-sm font-semibold text-white hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {uploading && (
                  <svg className="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
                  </svg>
                )}
                {uploading ? "Analysing…" : "Run Analysis"}
              </button>
              {uploading && <p className="text-xs text-slate-500">Profiling columns and generating proposals…</p>}
            </div>
          )}

          {errorMsg && (
            <div className="mt-4 rounded-xl border border-red-900 bg-red-950/40 px-4 py-3 text-sm text-red-300">
              {errorMsg}
            </div>
          )}
        </div>

        {/* Sample hint */}
        {queue.length === 0 && (
          <div className="mt-4 rounded-xl border border-dashed border-slate-800 px-5 py-4">
            <p className="text-xs text-slate-500">
              Sample files in <span className="font-mono text-slate-400">data/samples/</span> —{" "}
              <span className="font-mono">policies.csv</span>,{" "}
              <span className="font-mono">claims.csv</span>,{" "}
              <span className="font-mono">quotes.csv</span>,{" "}
              <span className="font-mono">risk_factors.csv</span>
            </p>
          </div>
        )}

      </main>
    </div>
  );
}
