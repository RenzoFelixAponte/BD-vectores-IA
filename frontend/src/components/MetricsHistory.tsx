import { RefreshCw, X } from "lucide-react";
import { useEffect, useState } from "react";
import {
  Bar, BarChart, CartesianGrid, Legend,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { api } from "../api/client";
import type { MetricsEntry } from "../types/api";

export function MetricsHistory() {
  const [entries, setEntries] = useState<MetricsEntry[]>([]);
  const [loading, setLoading] = useState(false);

  async function load() {
    setLoading(true);
    try { const res = await api.getMetricsHistory(20); setEntries(res.entries); }
    catch { /* ignore */ }
    finally { setLoading(false); }
  }

  async function clear() { await api.clearMetrics(); setEntries([]); }

  useEffect(() => { void load(); }, []);

  if (loading) return <p className="p-8 text-center text-slate-500 text-sm">Loading history…</p>;
  if (!entries.length) return <p className="p-8 text-center text-slate-500 text-sm">No query history yet.</p>;

  const chartData = entries.map((e, i) => ({
    name: `${i + 1}. ${e.operation}`,
    Reads: e.reads,
    Writes: e.writes,
  }));

  return (
    <div className="p-4 space-y-4">

      {/* Chart header */}
      <div className="flex items-center justify-between">
        <span className="text-xs text-slate-400">Last {entries.length} operations</span>
        <div className="flex gap-2">
          <button onClick={load} title="Refresh"
            className="p-1 rounded text-slate-400 hover:text-slate-100 hover:bg-slate-700 transition-colors">
            <RefreshCw size={13} />
          </button>
          <button onClick={clear} title="Clear"
            className="p-1 rounded text-slate-400 hover:text-red-400 hover:bg-slate-700 transition-colors">
            <X size={13} />
          </button>
        </div>
      </div>

      {/* Bar chart */}
      <div className="bg-slate-800/60 rounded-lg p-3 border border-slate-700">
        <ResponsiveContainer width="100%" height={180}>
          <BarChart data={chartData} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis dataKey="name" tick={{ fill: "#94a3b8", fontSize: 10 }} />
            <YAxis tick={{ fill: "#94a3b8", fontSize: 10 }} />
            <Tooltip contentStyle={{ background: "#1e293b", border: "1px solid #334155", color: "#f1f5f9", borderRadius: 6 }} />
            <Legend wrapperStyle={{ color: "#94a3b8", fontSize: 11 }} />
            <Bar dataKey="Reads"  fill="#60a5fa" radius={[3, 3, 0, 0]} />
            <Bar dataKey="Writes" fill="#f59e0b" radius={[3, 3, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Table */}
      <div className="overflow-auto rounded-lg border border-slate-700 max-h-52">
        <table className="w-full text-xs border-collapse">
          <thead>
            <tr className="bg-slate-800 sticky top-0">
              {["#","Op","Table","Reads","Writes","Rows","ms"].map((h) => (
                <th key={h} className="px-3 py-2 text-left text-[10px] font-semibold uppercase tracking-wider text-slate-400 border-b border-slate-700">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {[...entries].reverse().map((e, i) => (
              <tr key={i} className={`border-b border-slate-800 hover:bg-slate-700/30 transition-colors ${i % 2 === 0 ? "bg-slate-900" : "bg-slate-900/60"}`}>
                <td className="px-3 py-1.5 text-slate-500">{entries.length - i}</td>
                <td className="px-3 py-1.5">
                  <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-blue-950 text-blue-400">{e.operation}</span>
                </td>
                <td className="px-3 py-1.5 text-slate-300">{e.table}</td>
                <td className="px-3 py-1.5 text-blue-400">{e.reads}</td>
                <td className="px-3 py-1.5 text-amber-400">{e.writes}</td>
                <td className="px-3 py-1.5 text-slate-300">{e.row_count}</td>
                <td className="px-3 py-1.5 text-emerald-400">{e.time_ms}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
