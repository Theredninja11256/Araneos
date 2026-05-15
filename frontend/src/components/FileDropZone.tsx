import { useRef, useState, DragEvent, ChangeEvent } from "react";

interface Props {
  onFilesSelected: (files: File[]) => void;
  disabled?: boolean;
}

export default function FileDropZone({ onFilesSelected, disabled }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);

  function collectFiles(fileList: FileList | null): File[] {
    if (!fileList) return [];
    return Array.from(fileList).filter((f) => {
      const ext = f.name.split(".").pop()?.toLowerCase();
      return ["csv", "xlsx", "xls"].includes(ext ?? "");
    });
  }

  function handleDragOver(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    if (!disabled) setIsDragging(true);
  }

  function handleDragLeave() { setIsDragging(false); }

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setIsDragging(false);
    if (disabled) return;
    const files = collectFiles(e.dataTransfer.files);
    if (files.length > 0) onFilesSelected(files);
  }

  function handleChange(e: ChangeEvent<HTMLInputElement>) {
    const files = collectFiles(e.target.files);
    if (files.length > 0) onFilesSelected(files);
    e.target.value = "";
  }

  return (
    <div
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      onClick={() => !disabled && inputRef.current?.click()}
      className={[
        "flex flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed px-8 py-12 transition-colors cursor-pointer select-none",
        isDragging
          ? "border-blue-500 bg-blue-950/30"
          : "border-slate-700 bg-slate-900 hover:border-blue-600 hover:bg-slate-800/60",
        disabled ? "opacity-40 cursor-not-allowed" : "",
      ].join(" ")}
    >
      <svg className="h-8 w-8 text-slate-500" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
      </svg>
      <div className="text-center">
        <p className="text-sm font-medium text-slate-300">
          Drop files here or{" "}
          <span className="text-blue-400">browse</span>
        </p>
        <p className="mt-1 text-xs text-slate-500">CSV · XLSX · XLS</p>
      </div>
      <input
        ref={inputRef}
        type="file"
        multiple
        accept=".csv,.xlsx,.xls"
        className="hidden"
        onChange={handleChange}
        disabled={disabled}
      />
    </div>
  );
}
