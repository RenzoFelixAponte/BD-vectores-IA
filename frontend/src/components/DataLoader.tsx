import { useEffect, useState } from "react";
import { Folder, ChevronRight, Upload, Hammer, RefreshCw } from "lucide-react";
import { api } from "../api/client";
import type { FsResponse, TableInfo } from "../types/api";

interface Props { tables: TableInfo[]; onChanged: () => void; }

const SOURCES = ["file_path", "subfolder", "filename", "autoincrement", "empty"];

export function DataLoader({ tables, onChanged }: Props) {
  const [fs, setFs] = useState<FsResponse | null>(null);
  const [pathInput, setPathInput] = useState("");
  const [table, setTable] = useState(tables[0]?.name ?? "");
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [limit, setLimit] = useState<string>("");
  const [copy, setCopy] = useState(true);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  const current = tables.find(t => t.name === table);

  function goTo(path: string) {
    setMsg("");
    api.browseFs(path).then(r => { setFs(r); setPathInput(r.path); })
      .catch(e => setMsg("Error: " + String(e.message)));
  }

  useEffect(() => { goTo(""); }, []);
  useEffect(() => {
    if (!current) return;
    const m: Record<string, string> = {};
    for (const c of current.columns) {
      if (c.type === "AUDIO" || c.type === "IMAGE") m[c.name] = "file_path";
      else if (c.name === current.primary_key) m[c.name] = "autoincrement";
      else if (c.type === "CHAR") m[c.name] = "subfolder";
      else m[c.name] = "empty";
    }
    setMapping(m);
  }, [table, tables]);

  async function load() {
    if (!fs || !current) return;
    setBusy(true); setMsg("");
    try {
      const res = await api.loadFolder({
        table, folder: fs.path, mapping, copy,
        limit_per_subfolder: limit ? Number(limit) : null,
      });
      setMsg(`✓ ${res.inserted} filas insertadas en ${table}${res.copied ? " (archivos copiados al proyecto)" : ""}`);
      onChanged();
    } catch (e) { setMsg("Error: " + (e as Error).message); }
    finally { setBusy(false); }
  }

  async function buildIndex(column: string, type: string) {
    setBusy(true); setMsg("");
    const using = type === "INVERTED" ? "INVERTED" : "MULTIMEDIA";
    const name = `ix_${table}_${column}`;
    try {
      await api.executeQuery(`CREATE INDEX ${name} ON ${table} (${column}) USING ${using};`);
      setMsg(`✓ índice ${using} creado sobre ${column}`);
      onChanged();
    } catch (e) { setMsg("Error: " + (e as Error).message); }
    finally { setBusy(false); }
  }

  const contentCols = (current?.columns ?? []).filter(c => ["TEXT","IMAGE","AUDIO"].includes(c.type));

  return (
    <div className="p-4 space-y-4">
      <div className="bg-slate-900/40 border border-dashed border-slate-700 rounded-xl p-3 text-xs text-slate-400">
        Orden: <b className="text-slate-200">1) crear tabla</b> (Consola SQL) → <b className="text-slate-200">2) cargar datos</b> (aquí) → <b className="text-slate-200">3) construir índice</b>. El índice se construye sobre las filas ya cargadas.
      </div>

      <div className="bg-slate-800 border border-slate-700 rounded-xl p-4">
        <div className="flex items-center gap-2 font-semibold text-sm mb-3"><Upload size={16} className="text-blue-500"/> Cargar datos en una tabla</div>

        <div className="flex items-end gap-2 mb-3">
          <div className="flex-1">
            <label className="text-xs text-slate-400 block mb-1">tabla destino</label>
            <select value={table} onChange={e=>setTable(e.target.value)} className="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1.5 text-sm text-slate-100">
              {tables.map(t => <option key={t.name} value={t.name}>{t.name}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-slate-400 block mb-1">límite por subcarpeta (opcional)</label>
            <input value={limit} onChange={e=>setLimit(e.target.value)} placeholder="todas" className="w-32 bg-slate-900 border border-slate-700 rounded px-2 py-1.5 text-sm text-slate-100" />
          </div>
        </div>

        <label className="text-xs text-slate-400 block mb-1">carpeta de archivos — pega una ruta o navega</label>
        <div className="flex gap-2 mb-2">
          <input
            value={pathInput}
            onChange={e => setPathInput(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter") goTo(pathInput); }}
            placeholder="C:\\Users\\...\\gtzan\\Data\\genres_original"
            className="flex-1 bg-slate-900 border border-slate-700 rounded px-2 py-1.5 text-sm text-slate-100 font-mono"
          />
          <button onClick={() => goTo(pathInput)} className="px-3 py-1.5 text-sm rounded bg-blue-600 hover:bg-blue-700 text-white">ir</button>
        </div>
        <div className="bg-slate-900 border border-slate-700 rounded-lg p-2 mb-3">
          <div className="flex items-center gap-1 text-xs text-slate-400 mb-2 flex-wrap">
            <Folder size={13} className="text-blue-400" />
            <span className="truncate">{fs?.path ?? "…"}</span>
            {fs?.parent && <button onClick={()=>goTo(fs.parent!)} className="ml-2 text-slate-500 hover:text-slate-200">↑ subir</button>}
            <span className="ml-auto text-slate-500">{fs?.media_files ?? 0} archivos media aquí</span>
          </div>
          <div className="flex flex-wrap gap-1.5 max-h-40 overflow-auto">
            {fs?.dirs.map(d => (
              <button key={d.path} onClick={()=>goTo(d.path)}
                className="flex items-center gap-1 text-xs px-2 py-1 rounded border border-slate-700 text-slate-300 hover:border-blue-500">
                <Folder size={12} className="text-amber-400"/> {d.name} <ChevronRight size={11} className="text-slate-600"/>
              </button>
            ))}
            {fs && fs.dirs.length === 0 && <span className="text-xs text-slate-600">sin subcarpetas</span>}
          </div>
        </div>

        <label className="text-xs text-slate-400 block mb-1">mapeo de columnas — de dónde sale cada dato</label>
        <table className="w-full text-sm mb-3">
          <thead><tr className="text-slate-500 text-xs"><th className="text-left py-1">columna</th><th className="text-left py-1">se llena con</th></tr></thead>
          <tbody>
            {(current?.columns ?? []).map(c => (
              <tr key={c.name} className="border-t border-slate-700/60">
                <td className="py-1.5">{c.name} <span className="text-slate-500 italic text-xs">{c.type}</span></td>
                <td className="py-1.5">
                  <select value={mapping[c.name] ?? "empty"} onChange={e=>setMapping({...mapping, [c.name]: e.target.value})}
                    className="bg-slate-900 border border-slate-700 rounded px-2 py-1 text-xs text-slate-200">
                    {SOURCES.map(s => <option key={s} value={s}>{s}</option>)}
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <label className="flex items-center gap-2 text-xs text-slate-400 mb-2 cursor-pointer">
          <input type="checkbox" checked={copy} onChange={e=>setCopy(e.target.checked)} />
          copiar archivos al proyecto (back/data/media) — seguro y portable; si lo desmarcas solo guarda las rutas
        </label>
        <button onClick={load} disabled={busy || !fs} className="flex items-center gap-1.5 px-4 py-2 text-sm rounded bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-50">
          <Upload size={14}/> cargar datos
        </button>
      </div>

      <div className="bg-slate-800 border border-slate-700 rounded-xl p-4">
        <div className="flex items-center gap-2 font-semibold text-sm mb-3"><Hammer size={16} className="text-blue-500"/> Índices de contenido de <b>{table}</b></div>
        {contentCols.length === 0 && <p className="text-xs text-slate-500">Esta tabla no tiene columnas TEXT/IMAGE/AUDIO.</p>}
        {contentCols.map(c => {
          const type = c.type === "TEXT" ? "INVERTED" : "MULTIMEDIA";
          const built = current?.content_indexes?.some(i => i.columns.includes(c.name));
          return (
            <div key={c.name} className="flex items-center gap-3 bg-slate-900 rounded-lg px-3 py-2 mb-2">
              <b className="text-sm">{c.name}</b>
              <span className={`text-[11px] px-2 py-0.5 rounded-full ${type==="INVERTED"?"bg-cyan-900/60 text-cyan-300":"bg-violet-900/60 text-violet-300"}`}>{type}</span>
              <span className="text-xs text-slate-500">{type==="INVERTED"?"SPIMI + coseno":"MFCC/SIFT → K-Means → BoW"}</span>
              <span className="ml-auto">
                {built
                  ? <span className="text-xs text-green-400">✓ construido</span>
                  : <button onClick={()=>buildIndex(c.name, type)} disabled={busy} className="text-xs px-3 py-1 rounded border border-slate-600 text-slate-300 hover:border-blue-500 disabled:opacity-50">construir índice</button>}
              </span>
            </div>
          );
        })}
      </div>

      {msg && <div className={`text-sm px-1 ${msg.startsWith("Error")?"text-red-400":"text-green-400"}`}>{busy ? <RefreshCw size={13} className="inline animate-spin mr-1"/> : null}{msg}</div>}
      {busy && !msg && <div className="text-xs text-slate-500 px-1"><RefreshCw size={13} className="inline animate-spin mr-1"/>procesando…</div>}
    </div>
  );
}
