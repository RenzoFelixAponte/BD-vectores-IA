import { useRef, useState } from "react";
import { Upload, X, ChevronDown, Plus, Trash2 } from "lucide-react";
import { motion } from "framer-motion";
type FieldType = "INT" | "REAL" | "CHAR" | "BOOLEAN" | "IMAGE";

interface ColumnDef {
  name: string;
  type: FieldType;
  size: number;
  primaryKey: boolean;
}

interface SecondaryIndex {
  column: string;
  index_type: string;
}

interface Props {
  open: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

const INDEX_OPTIONS = [
  { value: "bplus",      label: "B+ Tree",           desc: "Búsqueda exacta y por rango" },
  { value: "sequential", label: "Sequential File",    desc: "Rango eficiente, archivo ordenado" },
  { value: "hashing",    label: "Extendible Hashing", desc: "Búsqueda exacta muy rápida" },
];

function inferType(values: string[]): { type: FieldType; size: number } {
  const nonEmpty = values.filter((v) => v.trim() !== "");
  if (nonEmpty.length === 0) return { type: "CHAR", size: 50 };
  if (nonEmpty.every((v) => /^-?\d+$/.test(v.trim()))) return { type: "INT", size: 4 };
  if (nonEmpty.every((v) => /^-?\d*\.?\d+([eE][+-]?\d+)?$/.test(v.trim()))) return { type: "REAL", size: 8 };
  if (nonEmpty.every((v) => /^(true|false|1|0)$/i.test(v.trim()))) return { type: "BOOLEAN", size: 1 };
  const maxLen = Math.max(...nonEmpty.map((v) => v.trim().length), 10);
  return { type: "CHAR", size: Math.min(Math.ceil(maxLen * 1.5), 255) };
}

function parseCsv(text: string): { headers: string[]; rows: string[][] } {
  const lines = text.replace(/\r\n/g, "\n").replace(/\r/g, "\n").trim().split("\n");
  if (lines.length === 0) return { headers: [], rows: [] };
  const headers = lines[0].split(",").map((h) => h.trim().replace(/^"|"$/g, ""));
  const rows = lines.slice(1, 51).map((l) =>
    l.split(",").map((v) => v.trim().replace(/^"|"$/g, ""))
  );
  return { headers, rows };
}

export function CsvUploadModal({ open, onClose, onSuccess }: Props) {
  const [step, setStep] = useState<"upload" | "configure">("upload");
  const [dragging, setDragging] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string[][]>([]);
  const [columns, setColumns] = useState<ColumnDef[]>([]);
  const [tableName, setTableName] = useState("");
  const [indexType, setIndexType] = useState("bplus");
  const [secondaryIndexes, setSecondaryIndexes] = useState<SecondaryIndex[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  function reset() {
    setStep("upload");
    setFile(null);
    setPreview([]);
    setColumns([]);
    setTableName("");
    setIndexType("bplus");
    setSecondaryIndexes([]);
    setError(null);
  }

  function handleClose() {
    reset();
    onClose();
  }

  function processFile(f: File) {
    setFile(f);
    setTableName(f.name.replace(/\.[^.]+$/, "").replace(/[^a-zA-Z0-9_]/g, "_").toLowerCase());
    const reader = new FileReader();
    reader.onload = (e) => {
      const text = e.target?.result as string;
      const { headers, rows } = parseCsv(text);
      if (headers.length === 0) { setError("CSV vacío o sin cabeceras"); return; }
      const cols: ColumnDef[] = headers.map((name, i) => {
        const colValues = rows.map((r) => r[i] ?? "");
        const { type, size } = inferType(colValues);
        return { name, type, size, primaryKey: i === 0 };
      });
      setColumns(cols);
      setPreview(rows.slice(0, 5));
      setError(null);
      setStep("configure");
    };
    reader.readAsText(f);
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files[0];
    if (f && f.name.endsWith(".csv")) processFile(f);
    else setError("Solo se aceptan archivos .csv");
  }

  function handleFileInput(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (f) processFile(f);
  }

  function setColField<K extends keyof ColumnDef>(idx: number, key: K, val: ColumnDef[K]) {
    setColumns((prev) => {
      const next = [...prev];
      if (key === "primaryKey" && val === true) {
        next.forEach((c, i) => { next[i] = { ...c, primaryKey: false }; });
      }
      next[idx] = { ...next[idx], [key]: val };
      return next;
    });
  }

  async function handleSubmit() {
    if (!file) return;
    if (!tableName.trim()) { setError("Ingresa un nombre de tabla"); return; }
    if (!columns.some((c) => c.primaryKey)) { setError("Selecciona una clave primaria"); return; }

    setLoading(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("table_name", tableName.trim());
      form.append("index_type", indexType);
      form.append("fields", JSON.stringify(
        columns.map((c) => ({ name: c.name, type: c.type, size: c.size, primary_key: c.primaryKey }))
      ));
      form.append("secondary_indexes", JSON.stringify(secondaryIndexes));
      const base = (import.meta.env.VITE_API_URL as string | undefined) ?? "/api/v1";
      const res = await fetch(`${base}/tables/upload`, { method: "POST", body: form });
      const body = await res.json();
      if (!res.ok) throw new Error(body?.detail ?? `HTTP ${res.status}`);
      onSuccess();
      handleClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95 }}
        className="bg-slate-800 border border-slate-700 rounded-xl shadow-2xl w-full max-w-2xl mx-4 max-h-[90vh] flex flex-col"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-700 shrink-0">
          <div>
            <h2 className="font-semibold text-slate-100">Importar desde CSV</h2>
            {step === "configure" && (
              <p className="text-xs text-slate-400 mt-0.5">{file?.name} — {columns.length} columnas detectadas</p>
            )}
          </div>
          <button onClick={handleClose} className="text-slate-400 hover:text-slate-200 transition-colors">
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-4">

          {/* STEP 1: Upload */}
          {step === "upload" && (
            <div
              onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={handleDrop}
              onClick={() => inputRef.current?.click()}
              className={`border-2 border-dashed rounded-xl p-12 flex flex-col items-center justify-center cursor-pointer transition-colors ${
                dragging ? "border-blue-500 bg-blue-500/10" : "border-slate-600 hover:border-slate-400"
              }`}
            >
              <Upload size={36} className="text-slate-400 mb-3" />
              <p className="text-slate-300 font-medium">Arrastra tu CSV aquí</p>
              <p className="text-slate-500 text-sm mt-1">o haz click para seleccionar</p>
              <input ref={inputRef} type="file" accept=".csv" className="hidden" onChange={handleFileInput} />
            </div>
          )}

          {/* STEP 2: Configure */}
          {step === "configure" && (
            <>
              {/* Table name + index type */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-slate-400 mb-1 block">Nombre de tabla</label>
                  <input
                    value={tableName}
                    onChange={(e) => setTableName(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-100 focus:outline-none focus:border-blue-500"
                  />
                </div>
                <div>
                  <label className="text-xs text-slate-400 mb-1 block">Tipo de índice</label>
                  <div className="relative">
                    <select
                      value={indexType}
                      onChange={(e) => setIndexType(e.target.value)}
                      className="w-full appearance-none bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-100 focus:outline-none focus:border-blue-500 pr-8"
                    >
                      {INDEX_OPTIONS.map((o) => (
                        <option key={o.value} value={o.value}>{o.label}</option>
                      ))}
                    </select>
                    <ChevronDown size={14} className="absolute right-2.5 top-2.5 text-slate-400 pointer-events-none" />
                  </div>
                  <p className="text-xs text-slate-500 mt-1">
                    {INDEX_OPTIONS.find((o) => o.value === indexType)?.desc}
                  </p>
                </div>
              </div>

              {/* Column configuration */}
              <div>
                <label className="text-xs text-slate-400 mb-2 block">Columnas detectadas</label>
                <div className="space-y-1.5">
                  {columns.map((col, i) => (
                    <div key={i} className="grid gap-2 items-center bg-slate-900 rounded-lg px-3 py-2" style={{ gridTemplateColumns: "1fr 110px 70px 80px" }}>
                      <span className="text-sm text-slate-200 font-mono truncate">{col.name}</span>
                      <select
                        value={col.type}
                        onChange={(e) => setColField(i, "type", e.target.value as FieldType)}
                        className="bg-slate-800 border border-slate-600 rounded px-2 py-1 text-xs text-slate-200 focus:outline-none focus:border-blue-500"
                      >
                        <option value="INT">INT</option>
                        <option value="REAL">REAL</option>
                        <option value="CHAR">CHAR</option>
                        <option value="BOOLEAN">BOOLEAN</option>
                        <option value="IMAGE">IMAGE</option>
                      </select>
                      {col.type === "CHAR" || col.type === "IMAGE" ? (
                        <input
                          type="number"
                          min={1} max={255}
                          value={col.size}
                          onChange={(e) => setColField(i, "size", Number(e.target.value))}
                          className="bg-slate-800 border border-slate-600 rounded px-2 py-1 text-xs text-slate-200 focus:outline-none focus:border-blue-500 w-full"
                        />
                      ) : (
                        <span className="text-xs text-slate-500 text-center">{col.size}B</span>
                      )}
                      <label className="flex items-center gap-1.5 cursor-pointer justify-end">
                        <input
                          type="radio"
                          name="primaryKey"
                          checked={col.primaryKey}
                          onChange={() => setColField(i, "primaryKey", true)}
                          className="accent-blue-500"
                        />
                        <span className="text-xs text-slate-400">PK</span>
                      </label>
                    </div>
                  ))}
                </div>
              </div>

              {/* Secondary indexes */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-xs text-slate-400">Índices secundarios (opcional)</label>
                  <button
                    type="button"
                    onClick={() => setSecondaryIndexes((p) => [...p, { column: columns[0]?.name ?? "", index_type: "bplus" }])}
                    className="flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 transition-colors"
                  >
                    <Plus size={12} /> Agregar índice
                  </button>
                </div>
                <div className="space-y-1.5">
                  {secondaryIndexes.map((si, i) => (
                    <div key={i} className="flex gap-2 items-center bg-slate-900 rounded-lg px-3 py-2">
                      <select
                        value={si.column}
                        onChange={(e) => setSecondaryIndexes((p) => p.map((x, j) => j === i ? { ...x, column: e.target.value } : x))}
                        className="flex-1 bg-slate-800 border border-slate-600 rounded px-2 py-1 text-xs text-slate-200 focus:outline-none focus:border-blue-500"
                      >
                        {columns.map((c) => <option key={c.name} value={c.name}>{c.name}</option>)}
                      </select>
                      <div className="relative">
                        <select
                          value={si.index_type}
                          onChange={(e) => setSecondaryIndexes((p) => p.map((x, j) => j === i ? { ...x, index_type: e.target.value } : x))}
                          className="appearance-none bg-slate-800 border border-slate-600 rounded px-2 py-1 text-xs text-slate-200 focus:outline-none focus:border-blue-500 pr-6"
                        >
                          {INDEX_OPTIONS.map((o) => (
                            <option key={o.value} value={o.value}>{o.label}</option>
                          ))}
                        </select>
                        <ChevronDown size={10} className="absolute right-1.5 top-2 text-slate-400 pointer-events-none" />
                      </div>
                      <button
                        type="button"
                        onClick={() => setSecondaryIndexes((p) => p.filter((_, j) => j !== i))}
                        className="text-slate-500 hover:text-red-400 transition-colors"
                      >
                        <Trash2 size={13} />
                      </button>
                    </div>
                  ))}
                  {secondaryIndexes.length === 0 && (
                    <p className="text-xs text-slate-600 italic">Sin índices secundarios</p>
                  )}
                </div>
              </div>

              {/* Preview */}
              {preview.length > 0 && (
                <div>
                  <label className="text-xs text-slate-400 mb-2 block">Vista previa (primeras {preview.length} filas)</label>
                  <div className="overflow-x-auto rounded-lg border border-slate-700">
                    <table className="text-xs w-full">
                      <thead>
                        <tr className="bg-slate-900">
                          {columns.map((c) => (
                            <th key={c.name} className="px-3 py-1.5 text-left text-slate-400 font-medium whitespace-nowrap">{c.name}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {preview.map((row, ri) => (
                          <tr key={ri} className="border-t border-slate-800 hover:bg-slate-800/50">
                            {row.map((cell, ci) => (
                              <td key={ci} className="px-3 py-1.5 text-slate-300 whitespace-nowrap">{cell}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </>
          )}

          {/* Error */}
          {error && (
            <p className="text-red-400 text-sm bg-red-900/20 border border-red-800/50 rounded-lg px-3 py-2">{error}</p>
          )}
        </div>

        {/* Footer */}
        {step === "configure" && (
          <div className="flex items-center justify-between px-5 py-4 border-t border-slate-700 shrink-0">
            <button
              onClick={() => { setStep("upload"); setFile(null); }}
              className="text-sm text-slate-400 hover:text-slate-200 transition-colors"
            >
              ← Cambiar archivo
            </button>
            <button
              onClick={handleSubmit}
              disabled={loading}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg text-sm font-medium transition-colors"
            >
              {loading ? (
                <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              ) : (
                <Upload size={14} />
              )}
              {loading ? "Importando..." : "Crear tabla e importar"}
            </button>
          </div>
        )}
      </motion.div>
    </div>
  );
}
