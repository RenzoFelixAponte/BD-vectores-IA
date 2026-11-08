import { AnimatePresence, motion } from "framer-motion";
import { ChevronDown, ChevronRight, RefreshCw, Table2, Trash2 } from "lucide-react";
import { useState } from "react";
import type { TableInfo } from "../types/api";
import { ConfirmModal } from "./ConfirmModal";

const INDEX_BADGE: Record<string, { label: string; color: string }> = {
  sequential: { label: "SEQ",   color: "#64748b" },
  isam:       { label: "ISAM",  color: "#0891b2" },
  bplus:      { label: "B+T",   color: "#16a34a" },
  hash:       { label: "HASH",  color: "#d97706" },
  hashing:    { label: "HASH",  color: "#d97706" },
  multimedia: { label: "IMG",   color: "#0891b2" },
};

interface Props {
  tables: TableInfo[];
  loading: boolean;
  onRefresh: () => void;
  onDrop: (name: string) => void;
  onSelectTable: (t: TableInfo) => void;
  selectedTable: string | null;
}

export function Sidebar({ tables, loading, onRefresh, onDrop, onSelectTable, selectedTable }: Props) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const [dropTarget, setDropTarget] = useState<string | null>(null);

  return (
    <>
      <aside className="flex flex-col overflow-hidden bg-slate-800 border-r border-slate-700">

        {/* Header */}
        <div className="flex items-center justify-between px-3 py-2.5 border-b border-slate-700 shrink-0">
          <span className="text-[10px] font-semibold uppercase tracking-widest text-slate-400">Tables</span>
          <button
            onClick={onRefresh}
            disabled={loading}
            title="Refresh"
            className="p-1 rounded text-slate-400 hover:text-slate-100 hover:bg-slate-700 disabled:opacity-40 transition-colors"
          >
            <RefreshCw size={13} className={loading ? "spin" : ""} />
          </button>
        </div>

        {tables.length === 0 && !loading && (
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="px-3 py-4 text-xs text-slate-500"
          >
            No tables yet.
          </motion.p>
        )}

        {/* Table list */}
        <ul className="overflow-y-auto flex-1">
          <AnimatePresence initial={false}>
            {tables.map((t, i) => {
              const badge = INDEX_BADGE[t.primary_index_type] ?? { label: t.primary_index_type, color: "#64748b" };
              const isOpen = expanded === t.name;
              const isActive = selectedTable === t.name;

              return (
                <motion.li
                  key={t.name}
                  initial={{ opacity: 0, x: -12 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -12, height: 0 }}
                  transition={{ duration: 0.18, delay: i * 0.04 }}
                  className="border-b border-slate-700/60"
                >
                  {/* Row */}
                  <div
                    onClick={() => { onSelectTable(t); setExpanded(isOpen ? null : t.name); }}
                    className={`flex items-center gap-1.5 px-2.5 py-2 cursor-pointer transition-colors ${
                      isActive ? "bg-slate-700/60" : "hover:bg-slate-700/40"
                    }`}
                  >
                    <Table2 size={13} className="text-slate-500 shrink-0" />
                    <span className="flex-1 text-[13px] truncate">{t.name}</span>
                    <span className="index-badge" style={{ backgroundColor: badge.color }}>{badge.label}</span>
                    {isOpen
                      ? <ChevronDown size={12} className="text-slate-500 shrink-0" />
                      : <ChevronRight size={12} className="text-slate-500 shrink-0" />
                    }
                  </div>

                  {/* Detail panel */}
                  <AnimatePresence initial={false}>
                    {isOpen && (
                      <motion.div
                        key="detail"
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: "auto", opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.2, ease: "easeInOut" }}
                        className="overflow-hidden"
                      >
                        <div className="px-3 pb-3 pt-1 bg-slate-900/40">
                          <ul className="space-y-0.5 mb-2">
                            {t.columns.map((c) => {
                              const secIdx = t.secondary_indexes?.find(idx => idx.columns.includes(c.name));
                              const contentIdx = t.content_indexes?.find(idx => idx.columns.includes(c.name));
                              const anyIdx = secIdx ?? contentIdx;
                              return (
                                <li key={c.name} className="flex justify-between text-xs py-0.5 gap-1">
                                  <span className="text-slate-300 truncate">{c.name}</span>
                                  <span className="flex items-center gap-1 shrink-0">
                                    <span className="text-slate-500 italic">{c.type}</span>
                                    {anyIdx && (
                                      <span className="px-1 py-px text-[9px] font-bold rounded bg-amber-800/60 text-amber-300 border border-amber-700/50">
                                        2°{anyIdx.type.toUpperCase().slice(0, 3)}
                                      </span>
                                    )}
                                  </span>
                                </li>
                              );
                            })}
                          </ul>
                          <div className="flex gap-1.5 mt-2">
                            <button
                              onClick={() => setDropTarget(t.name)}
                              className="flex items-center gap-1 px-2 py-1 text-[11px] rounded border border-slate-600 text-slate-300 hover:border-red-500 hover:text-red-400 transition-colors"
                            >
                              <Trash2 size={11} /> Drop
                            </button>
                          </div>
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </motion.li>
              );
            })}
          </AnimatePresence>
        </ul>
      </aside>

      {/* Confirm modal */}
      <ConfirmModal
        open={dropTarget !== null}
        title="Drop Table"
        message={`Are you sure you want to drop "${dropTarget}"? This will permanently delete all its records and index files.`}
        confirmLabel="Drop Table"
        cancelLabel="Cancel"
        variant="danger"
        onConfirm={() => { if (dropTarget) onDrop(dropTarget); setDropTarget(null); }}
        onCancel={() => setDropTarget(null)}
      />
    </>
  );
}
