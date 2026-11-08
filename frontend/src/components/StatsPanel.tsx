import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle } from "lucide-react";
import type { QueryResult } from "../types/api";

interface StatProps {
  label: string;
  value: number | string;
  unit?: string;
  valueClass?: string;
  delay?: number;
}

function Stat({ label, value, unit, valueClass = "text-slate-100", delay = 0 }: StatProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.22, delay }}
      className="flex flex-col items-center px-5 py-2 border-r border-slate-700 min-w-[88px]"
    >
      <span className="text-[10px] font-semibold uppercase tracking-widest text-slate-500">{label}</span>
      <span className={`text-lg font-bold mt-0.5 tabular-nums ${valueClass}`}>
        {value}
        {unit && <span className="text-xs font-normal text-slate-500 ml-1">{unit}</span>}
      </span>
    </motion.div>
  );
}

interface Props {
  result: QueryResult | null;
  error: string | null;
}

export function StatsPanel({ result, error }: Props) {
  return (
    <div className="shrink-0 border-b border-slate-700 min-h-[52px]">
      <AnimatePresence mode="wait">

        {error && (
          <motion.div
            key="error"
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.2 }}
            className="flex items-start gap-2.5 px-4 py-2.5 bg-red-950/40 border-b border-red-900/60"
          >
            <AlertTriangle size={15} className="text-red-400 mt-0.5 shrink-0" />
            <pre className="text-xs text-red-300 font-mono whitespace-pre-wrap break-all">{error}</pre>
          </motion.div>
        )}

        {!error && !result && (
          <motion.div
            key="empty"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="px-4 py-2.5 text-xs text-slate-500 bg-slate-800/50"
          >
            Run a query to see execution statistics.
          </motion.div>
        )}

        {!error && result && (
          <motion.div
            key={`stats-${result.time_ms}`}
            className="flex items-center overflow-x-auto bg-slate-800/60"
          >
            <Stat label="Rows"        value={result.row_count}               valueClass="text-green-400"   delay={0} />
            <Stat label="Disk Reads"  value={result.reads}   unit="pages"    valueClass="text-blue-400"    delay={0.04} />
            <Stat label="Disk Writes" value={result.writes}  unit="pages"    valueClass="text-amber-400"   delay={0.08} />
            <Stat label="Total I/O"   value={result.reads + result.writes} unit="pages" valueClass="text-violet-400" delay={0.12} />
            <Stat label="Time"        value={result.time_ms.toFixed(2)} unit="ms" valueClass="text-emerald-400" delay={0.16} />
            {result.message && (
              <motion.span
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.2 }}
                className="px-4 text-xs text-emerald-400 flex-1"
              >
                {result.message}
              </motion.span>
            )}
          </motion.div>
        )}

      </AnimatePresence>
    </div>
  );
}
