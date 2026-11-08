import { useMemo, useState } from "react";
import { Music, Search, Upload, Waves } from "lucide-react";
import { api } from "../api/client";
import type { SearchHit, TableInfo } from "../types/api";

type Mode = "texto" | "audio";

const GENRES = ["blues","classical","country","disco","hiphop","jazz","metal","pop","reggae","rock"];

interface Props { tables: TableInfo[]; }

export function MusicSearch({ tables }: Props) {
  const musicTables = useMemo(
    () => tables.filter(t => t.content_indexes?.some(i => i.type === "multimedia" || i.type === "inverted")),
    [tables]
  );
  const [table, setTable] = useState(musicTables[0]?.name ?? "");
  const current = tables.find(t => t.name === table);
  const audioCol = current?.content_indexes?.find(i => i.type === "multimedia")?.columns[0] ?? null;
  const textCol = current?.content_indexes?.find(i => i.type === "inverted")?.columns[0] ?? null;

  const [mode, setMode] = useState<Mode>("audio");
  const [method, setMethod] = useState<string | null>(null);
  const [genre, setGenre] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [k, setK] = useState(10);
  const [rows, setRows] = useState<SearchHit[]>([]);
  const [info, setInfo] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  async function run() {
    setErr(""); setLoading(true);
    try {
      if (mode === "audio") {
        if (!file || !audioCol) { setErr("Sube un audio y asegúrate de tener índice MULTIMEDIA"); return; }
        const res = await api.searchMedia(file, { table, column: audioCol, k, method, genre });
        setRows(res.rows); setInfo(`${res.rows.length} resultados · ${res.time_ms} ms`);
      } else {
        if (!text || !textCol) { setErr("Escribe texto y asegúrate de tener índice INVERTED"); return; }
        const res = await api.searchText({ table, column: textCol, query: text, k, method, genre });
        setRows(res.rows); setInfo(`${res.rows.length} resultados · ${res.time_ms} ms`);
      }
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
          <Music size={16} className="text-blue-500" /> Búsqueda musical
        </div>

        <div className="flex flex-wrap items-center gap-2 mb-3">
          <span onClick={() => setMode("texto")} className={chip(mode==="texto")}>por letra/género (@@)</span>
          <span onClick={() => setMode("audio")} className={chip(mode==="audio")}>por audio (&lt;-&gt;)</span>
          <div className="ml-auto flex items-center gap-2">
            <select value={table} onChange={e=>setTable(e.target.value)} className="bg-slate-900 border border-slate-700 rounded px-2 py-1 text-xs text-slate-200">
              {musicTables.map(t => <option key={t.name} value={t.name}>{t.name}</option>)}
            </select>
            <span className="text-xs text-slate-500">motor:</span>
            <span onClick={()=>setMethod(null)} className={chip(method===null)}>propio</span>
            <span onClick={()=>setMethod("sequential")} className={chip(method==="sequential")}>secuencial</span>
          </div>
        </div>

        {mode === "texto" ? (
          <div className="flex gap-2 mb-3">
            <input value={text} onChange={e=>setText(e.target.value)} placeholder="palabras de la letra o género (ej: guitarra ritmo lento)…"
              className="flex-1 bg-slate-900 border border-slate-700 rounded px-3 py-2 text-sm text-slate-100" />
            <button onClick={run} disabled={loading} className="flex items-center gap-1.5 px-4 py-2 text-sm rounded bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-50">
              <Search size={14}/> buscar
            </button>
          </div>
        ) : (
          <div className="flex gap-3 items-stretch mb-3">
            <label className="flex-1 border border-dashed border-slate-600 rounded-lg bg-slate-900 flex flex-col items-center justify-center py-5 cursor-pointer hover:border-blue-500">
              <Upload size={22} className="text-slate-500" />
              <span className="text-xs text-slate-400 mt-1">{file ? file.name : "arrastra o sube un audio (.wav/.mp3)"}</span>
              <input type="file" accept="audio/*" className="hidden" onChange={e=>setFile(e.target.files?.[0] ?? null)} />
            </label>
            <button onClick={run} disabled={loading} className="flex items-center gap-1.5 px-4 text-sm rounded bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-50">
              <Search size={14}/> buscar similares
            </button>
          </div>
        )}

        {file && mode === "audio" && (
          <div className="bg-slate-900 border border-slate-700 rounded-lg p-2 mb-3 flex items-center gap-3">
            <Waves size={16} className="text-blue-400" />
            <span className="text-xs text-slate-400">{file.name} · consulta</span>
            <audio controls src={URL.createObjectURL(file)} className="h-8 ml-auto" />
          </div>
        )}

        <div className="flex flex-wrap items-center gap-1.5 mb-1">
          <span className="text-xs text-slate-500">filtrar por género:</span>
          <span onClick={()=>setGenre(null)} className={chip(genre===null)}>todos</span>
          {GENRES.map(g => <span key={g} onClick={()=>setGenre(g)} className={chip(genre===g)}>{g}</span>)}
          <span className="ml-auto text-xs text-slate-500">top-k</span>
          <input type="range" min={5} max={20} value={k} onChange={e=>setK(+e.target.value)} className="w-24" />
          <span className="text-xs text-green-400 w-5">{k}</span>
        </div>
      </div>

      {err && <div className="text-sm text-red-400 px-1">{err}</div>}
      {info && <div className="text-xs text-slate-500 px-1">{info}</div>}

      <div className="space-y-2">
        {rows.map((row) => {
          const pathVal = audioCol ? String(row[audioCol] ?? "") : "";
          return (
            <div key={String(row._rank)} className="flex items-center gap-3 bg-slate-800 border border-slate-700 rounded-lg px-3 py-2">
              <span className="text-xs text-slate-500 w-5">{row._rank}</span>
              <div className="flex-1 min-w-0">
                <div className="text-sm truncate">{String(row["track_name"] ?? row[audioCol ?? ""] ?? row["id"]).split(/[\\/]/).pop()}</div>
                {pathVal && <audio controls src={api.mediaUrl(pathVal)} className="h-7 mt-1 w-full max-w-md" />}
              </div>
              {row["genero"] != null && <span className="text-[11px] px-2 py-0.5 rounded-full bg-amber-900/50 text-amber-300">{String(row["genero"])}</span>}
              <span className={`text-sm ${row._score >= 0.99 ? "text-green-400" : "text-slate-400"}`}>{row._score.toFixed(2)}</span>
            </div>
          );
        })}
        {!rows.length && !loading && <p className="text-center text-slate-600 text-sm py-8">Sube un audio o escribe una letra y pulsa buscar.</p>}
      </div>
    </div>
  );
}
