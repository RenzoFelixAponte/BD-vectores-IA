import { useMemo, useState } from "react";
import { Image as ImageIcon, Search, Upload } from "lucide-react";
import { api } from "../api/client";
import type { SearchHit, TableInfo } from "../types/api";

interface Props { tables: TableInfo[]; }

export function VisualSearch({ tables }: Props) {
  const imageTables = useMemo(
    () => tables.filter(t =>
      t.content_indexes?.some(i => i.type === "multimedia") &&
      t.columns.some(c => c.type === "IMAGE")),
    [tables]
  );
  const [table, setTable] = useState(imageTables[0]?.name ?? "");
  const current = tables.find(t => t.name === table);
  const imageCol = current?.content_indexes?.find(i => i.type === "multimedia")?.columns[0] ?? null;

  const [method, setMethod] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [k, setK] = useState(10);
  const [rows, setRows] = useState<SearchHit[]>([]);
  const [info, setInfo] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  async function run() {
    setErr(""); setLoading(true);
    try {
      if (!file || !imageCol) { setErr("Sube una imagen y asegúrate de tener índice MULTIMEDIA sobre una columna IMAGE"); return; }
      const res = await api.searchMedia(file, { table, column: imageCol, k, method });
      setRows(res.rows); setInfo(`${res.rows.length} resultados · ${res.time_ms} ms`);
    } catch (e) { setErr(String((e as Error).message)); }
    finally { setLoading(false); }
  }

  const chip = (on: boolean) =>
    `text-xs px-3 py-1.5 rounded-full border cursor-pointer transition-colors ${
      on ? "bg-blue-600/20 border-blue-500 text-blue-300" : "border-slate-600 text-slate-400 hover:text-slate-200"}`;

  return (
    <div className="p-4 space-y-4">
      <div className="bg-slate-800 border border-slate-700 rounded-xl p-4">
        <div className="flex items-center gap-2 font-semibold text-sm mb-3">
          <ImageIcon size={16} className="text-blue-500" /> Búsqueda visual
          <span className="text-[11px] text-slate-500 font-normal font-mono ml-1">SELECT * FROM {table || "tabla"} WHERE {imageCol || "foto"} &lt;-&gt; 'consulta' LIMIT {k}</span>
        </div>

        <div className="flex flex-wrap items-center gap-2 mb-4">
          <select value={table} onChange={e=>setTable(e.target.value)} className="bg-slate-900 border border-slate-700 rounded px-2 py-1 text-xs text-slate-200">
            {imageTables.map(t => <option key={t.name} value={t.name}>{t.name}</option>)}
          </select>
          <span className="text-xs text-slate-500">motor:</span>
          <span onClick={()=>setMethod(null)} className={chip(method===null)}>propio</span>
          <span onClick={()=>setMethod("sequential")} className={chip(method==="sequential")}>secuencial</span>
          <div className="ml-auto flex items-center gap-2">
            <span className="text-xs text-slate-500">top-k</span>
            <input type="range" min={5} max={20} value={k} onChange={e=>setK(+e.target.value)} className="w-24" />
            <span className="text-xs text-green-400 w-5">{k}</span>
          </div>
        </div>

        <div className="grid gap-3" style={{ gridTemplateColumns: "180px 1fr" }}>
          <div>
            <label className="border border-dashed border-slate-600 rounded-lg bg-slate-900 flex flex-col items-center justify-center py-6 cursor-pointer hover:border-blue-500">
              <Upload size={24} className="text-slate-500" />
              <span className="text-xs text-slate-400 mt-1.5">sube una foto</span>
              <input type="file" accept="image/*" className="hidden" onChange={e=>setFile(e.target.files?.[0] ?? null)} />
            </label>
            {file && <img src={URL.createObjectURL(file)} alt="consulta" className="mt-2 rounded-lg w-full h-32 object-cover" />}
            <button onClick={run} disabled={loading} className="mt-2 w-full flex items-center justify-center gap-1.5 px-3 py-2 text-sm rounded bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-50">
              <Search size={14}/> buscar similares
            </button>
          </div>

          <div className="grid gap-2" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(110px, 1fr))" }}>
            {rows.map((row) => {
              const pathVal = imageCol ? String(row[imageCol] ?? "") : "";
              return (
                <div key={String(row._rank)} className="bg-slate-900 border border-slate-700 rounded-lg p-1.5">
                  <img src={api.mediaUrl(pathVal)} alt="" className="w-full h-20 object-cover rounded" />
                  <div className="flex justify-between items-center mt-1">
                    <span className="text-[11px] text-slate-400 truncate">#{row._rank}</span>
                    <span className={`text-[11px] ${row._score >= 0.99 ? "text-green-400" : "text-slate-400"}`}>{row._score.toFixed(2)}</span>
                  </div>
                </div>
              );
            })}
            {!rows.length && !loading && <p className="col-span-full text-center text-slate-600 text-sm py-8">Sube una foto y pulsa buscar.</p>}
          </div>
        </div>
      </div>
      {err && <div className="text-sm text-red-400 px-1">{err}</div>}
      {info && <div className="text-xs text-slate-500 px-1">{info}</div>}
    </div>
  );
}
