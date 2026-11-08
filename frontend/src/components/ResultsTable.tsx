import { AnimatePresence, motion } from "framer-motion";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useState } from "react";
import { api } from "../api/client";

const PAGE_SIZE = 50;

const AUDIO_EXT = [".wav", ".mp3", ".ogg", ".flac", ".au", ".m4a", ".aac"];
const IMAGE_EXT = [".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"];

function renderCell(value: unknown) {
  const s = String(value ?? "");
  const low = s.toLowerCase();
  if (AUDIO_EXT.some((e) => low.endsWith(e))) {
    // Reproductor inline; preload="none" para no cargar todos los audios de golpe.
    return <audio controls preload="none" src={api.mediaUrl(s)} className="h-8 w-64 max-w-full" />;
  }
  if (IMAGE_EXT.some((e) => low.endsWith(e))) {
    return <img src={api.mediaUrl(s)} alt="" loading="lazy" className="h-14 w-14 object-cover rounded" />;
  }
  return s;
}

interface Props {
  columns: string[];
  rows: Record<string, unknown>[];
}

export function ResultsTable({ columns, rows }: Props) {
  const [page, setPage] = useState(0);

  if (columns.length === 0 && rows.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-slate-500 text-sm">
        No results to display.
      </div>
    );
  }

  const totalPages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  const visible = rows.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-1.5 bg-slate-800/80 border-b border-slate-700 shrink-0">
        <span className="text-xs text-slate-400 font-medium">
          {rows.length} row{rows.length !== 1 ? "s" : ""}
        </span>
        {totalPages > 1 && (
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="p-0.5 rounded text-slate-400 hover:text-slate-100 disabled:opacity-30 transition-colors"
            >
              <ChevronLeft size={16} />
            </button>
            <span className="text-xs text-slate-400 min-w-[60px] text-center">
              {page + 1} / {totalPages}
            </span>
            <button
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={page === totalPages - 1}
              className="p-0.5 rounded text-slate-400 hover:text-slate-100 disabled:opacity-30 transition-colors"
            >
              <ChevronRight size={16} />
            </button>
          </div>
        )}
      </div>

      {/* Table */}
      <div className="overflow-auto flex-1">
        <table className="results-table w-full border-collapse text-[13px]">
          <thead>
            <tr className="bg-slate-800">
              {columns.map((col) => (
                <th
                  key={col}
                  className="px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-wider text-slate-400 border-b border-slate-700 whitespace-nowrap"
                >
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <AnimatePresence mode="wait">
            <motion.tbody
              key={page}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
            >
              {visible.map((row, i) => (
                <motion.tr
                  key={i}
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.12, delay: i * 0.015 }}
                  className={`border-b border-slate-800 hover:bg-slate-700/40 transition-colors ${
                    i % 2 === 0 ? "bg-slate-900" : "bg-slate-900/60"
                  }`}
                >
                  {columns.map((col) => (
                    <td key={col} className="px-3 py-1.5 align-middle max-w-[320px] overflow-hidden text-ellipsis">
                      {renderCell(row[col])}
                    </td>
                  ))}
                </motion.tr>
              ))}
            </motion.tbody>
          </AnimatePresence>
        </table>
      </div>
    </div>
  );
}
