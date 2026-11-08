import { useMemo, useState } from "react";
import { FlaskConical, Play } from "lucide-react";
import { api } from "../api/client";
import type { ExperimentResponse, TableInfo } from "../types/api";

interface Props { tables: TableInfo[]; }

export function ExperimentRunner({ tables }: Props) {
  const indexed = useMemo(
    () => tables.filter(t => (t.content_indexes?.length ?? 0) > 0),
    [tables]
  );
  const [table, setTable] = useState(indexed[0]?.name ?? "");
  const current = tables.find(t => t.name === table);
  const idx = current?.content_indexes ?? [];
  const [indexName, setIndexName] = useState(idx[0]?.name ?? "");
  const chosen = idx.find(i => i.name === indexName) ?? idx[0];

  const [topK, setTopK] = useState(10);
  const [queries, setQueries] = useState(20);
  const [repeats, setRepeats] = useState(3);
  const [res, setRes] = useState<ExperimentResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function run() {
    if (!chosen) { setErr("La tabla no tiene índice de contenido."); return; }
    setBusy(true); setErr(""); setRes(null);
    try {
      const r = await api.runExperiment({
        table,
        column: chosen.columns[0],
        kind: chosen.type === "inverted" ? "text" : "media",
        engines: ["propio", "secuencial"],
        top_k: topK, queries, repeats,
      });
      setRes(r);
    } catch (e) { setErr(String((e as Error).message)); }
    finally { setBusy(false); }
  }

  const fmt = (v: number | null, d = 3) => v == null ? "—" : v.toFixed(d);

  return (
    <div className="p-4 space-y-4">
      <div className="bg-slate-800 border border-slate-700 rounded-xl p-4">
        <div className="flex items-center gap-2 font-semibold text-sm mb-3">
          <FlaskConical size={16} className="text-blue-500" /> Experimentos — comparar motores
        </div>
        <div className="grid gap-3 mb-3" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(140px,1fr))" }}>
          <div>
            <label className="text-xs text-slate-400 block mb-1">tabla</label>
            <select value={table} onChange={e=>setTable(e.target.value)} className="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1.5 text-sm text-slate-100">
              {indexed.map(t => <option key={t.name} value={t.name}>{t.name}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-slate-400 block mb-1">índice</label>
            <select value={indexName} onChange={e=>setIndexName(e.target.value)} className="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1.5 text-sm text-slate-100">
              {idx.map(i => <option key={i.name} value={i.name}>{i.columns[0]} · {i.type}</option>)}
            </select>
          </div>
          <div><label className="text-xs text-slate-400 block mb-1">top-k</label><input type="number" value={topK} onChange={e=>setTopK(+e.target.value)} className="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1.5 text-sm text-slate-100" /></div>
          <div><label className="text-xs text-slate-400 block mb-1"># consultas</label><input type="number" value={queries} onChange={e=>setQueries(+e.target.value)} className="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1.5 text-sm text-slate-100" /></div>
          <div><label className="text-xs text-slate-400 block mb-1">repeticiones</label><input type="number" value={repeats} onChange={e=>setRepeats(+e.target.value)} className="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1.5 text-sm text-slate-100" /></div>
        </div>
        <button onClick={run} disabled={busy || !chosen} className="flex items-center gap-1.5 px-4 py-2 text-sm rounded bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-50">
          <Play size={14}/> {busy ? "corriendo…" : "correr experimento"}
        </button>
        <p className="text-xs text-slate-500 mt-2">Compara índice propio vs. búsqueda secuencial sobre las mismas consultas (genero como proxy de precisión).</p>
      </div>

      {err && <div className="text-sm text-red-400 px-1">{err}</div>}

      {res && (
        <div className="bg-slate-800 border border-slate-700 rounded-xl p-4">
          <div className="text-xs text-slate-500 mb-3">{res.queries} consultas · top-{res.top_k} · {res.repeats} repeticiones · {res.kind}</div>
          <table className="w-full text-sm">
            <thead><tr className="text-slate-500 text-xs uppercase">
              <th className="text-left py-1.5">motor</th><th className="text-right">media ms</th><th className="text-right">mediana</th><th className="text-right">p95</th><th className="text-right">throughput</th><th className="text-right">precisión@k</th><th className="text-right">índice</th>
            </tr></thead>
            <tbody>
              {Object.entries(res.engines).map(([name, m]) => (
                <tr key={name} className="border-t border-slate-700/60">
                  <td className="py-2 font-medium">{name}</td>
                  <td className="text-right text-green-400">{fmt(m.mean_ms)}</td>
                  <td className="text-right">{fmt(m.median_ms)}</td>
                  <td className="text-right">{fmt(m.p95_ms)}</td>
                  <td className="text-right">{m.throughput_qps == null ? "—" : Math.round(m.throughput_qps).toLocaleString()} q/s</td>
                  <td className="text-right">{fmt(m.precision_at_k, 3)}</td>
                  <td className="text-right text-slate-500">{m.index_size ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
