import { AnimatePresence, motion } from "framer-motion";
import {
  ChevronDown,
  Database,
  FlaskConical,
  FolderInput,
  History,
  Image as ImageIcon,
  Music,
  TableProperties,
  Terminal,
  Upload,
} from "lucide-react";
import { useRef, useState } from "react";
import { CsvUploadModal } from "./components/CsvUploadModal";
import { DataLoader } from "./components/DataLoader";
import { ExperimentRunner } from "./components/ExperimentRunner";
import { ImageSearchPanel } from "./components/ImageSearchPanel";
import { MetricsHistory } from "./components/MetricsHistory";
import { MusicSearch } from "./components/MusicSearch";
import { ProductResultsGrid } from "./components/ProductResultsGrid";
import { ResultsTable } from "./components/ResultsTable";
import { Sidebar } from "./components/Sidebar";
import { SqlEditor } from "./components/SqlEditor";
import { StatsPanel } from "./components/StatsPanel";
import { useQuery } from "./hooks/useQuery";
import { useTables } from "./hooks/useTables";
import type { QueryResult, TableInfo } from "./types/api";

type Tab = "datos" | "visual" | "musical" | "experimentos" | "results" | "history";

const EXAMPLE_QUERIES = [
  `CREATE TABLE products (id INT PRIMARY KEY USING BPLUS TREE, name CHAR(80), image_path IMAGE);`,
  `CREATE INDEX idx_products_image ON products (image_path) USING MULTIMEDIA;`,
  `SELECT * FROM products WHERE image_path <-> 'datasets/query.jpg' LIMIT 10 USING MULTIMEDIA;`,
  `SELECT * FROM cancion WHERE pista <-> 'consulta.wav' LIMIT 10;`,
  `SELECT * FROM docs WHERE cuerpo @@ 'machine learning' LIMIT 10;`,
];

export default function App() {
  const [sql, setSql] = useState("");
  const [tab, setTab] = useState<Tab>("visual");
  const [termOpen, setTermOpen] = useState(true);
  const [terminalHeight, setTerminalHeight] = useState(270);
  const [selectedTable, setSelectedTable] = useState<string | null>(null);
  const [csvModalOpen, setCsvModalOpen] = useState(false);
  const [visualResult, setVisualResult] = useState<QueryResult | null>(null);
  const [visualImageColumn, setVisualImageColumn] = useState<string | null>(null);
  const resizeStart = useRef<{ y: number; height: number } | null>(null);

  const { result, error, loading, execute } = useQuery();
  const { tables, loading: tablesLoading, refresh, drop: dropTable } = useTables();

  async function drop(name: string) {
    await dropTable(name);
    if (selectedTable === name) setSelectedTable(null);
  }

  async function runQuery() {
    await execute(sql);
    await refresh();
    setTab("results");
  }

  function handleSelectTable(t: TableInfo) {
    setSelectedTable(t.name);
    setSql(`SELECT * FROM ${t.name};`);
    setTab("results");
  }

  function handleVisualResult(nextResult: QueryResult | null, imageColumn: string | null) {
    setVisualResult(nextResult);
    setVisualImageColumn(imageColumn);
    setTab("visual");
  }

  function startTerminalResize(event: React.PointerEvent<HTMLDivElement>) {
    if (!termOpen) return;
    event.preventDefault();
    resizeStart.current = { y: event.clientY, height: terminalHeight };
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function resizeTerminal(event: React.PointerEvent<HTMLDivElement>) {
    if (!resizeStart.current) return;
    const delta = resizeStart.current.y - event.clientY;
    const maxHeight = Math.round(window.innerHeight * 0.58);
    const nextHeight = Math.min(Math.max(resizeStart.current.height + delta, 150), maxHeight);
    setTerminalHeight(nextHeight);
  }

  function stopTerminalResize(event: React.PointerEvent<HTMLDivElement>) {
    resizeStart.current = null;
    event.currentTarget.releasePointerCapture(event.pointerId);
  }

  const shownResult = tab === "visual" ? visualResult : result;

  const tabs: { key: Tab; label: React.ReactNode }[] = [
    { key: "datos", label: <span className="flex items-center gap-1.5"><FolderInput size={13} />Datos</span> },
    {
      key: "visual",
      label: (
        <span className="flex items-center gap-1.5">
          <ImageIcon size={13} /> Visual
          {visualResult && (
            <span className="ml-0.5 bg-cyan-600 text-white text-[10px] font-bold px-1.5 py-px rounded-full">
              {visualResult.row_count}
            </span>
          )}
        </span>
      ),
    },
    { key: "musical", label: <span className="flex items-center gap-1.5"><Music size={13} />Musical</span> },
    { key: "experimentos", label: <span className="flex items-center gap-1.5"><FlaskConical size={13} />Experimentos</span> },
    {
      key: "results",
      label: (
        <span className="flex items-center gap-1.5">
          <TableProperties size={13} /> Resultados
          {result && (
            <span className="ml-0.5 bg-blue-600 text-white text-[10px] font-bold px-1.5 py-px rounded-full">
              {result.row_count}
            </span>
          )}
        </span>
      ),
    },
    { key: "history", label: <span className="flex items-center gap-1.5"><History size={13} />Historial</span> },
  ];

  return (
    <div className="grid h-screen overflow-hidden bg-slate-900 text-slate-100" style={{ gridTemplateColumns: "220px 1fr" }}>
      <CsvUploadModal open={csvModalOpen} onClose={() => setCsvModalOpen(false)} onSuccess={refresh} />

      <Sidebar
        tables={tables}
        loading={tablesLoading}
        onRefresh={refresh}
        onDrop={drop}
        onSelectTable={handleSelectTable}
        selectedTable={selectedTable}
      />

      <main className="flex flex-col overflow-hidden">
        <header className="flex items-center justify-between px-4 py-2.5 bg-slate-800 border-b border-slate-700 shrink-0">
          <div className="flex items-center gap-2 font-bold text-[15px] tracking-wide">
            <Database size={18} className="text-blue-500" />
            Multimodal Product Search
          </div>
          <button
            onClick={() => setCsvModalOpen(true)}
            className="flex items-center gap-1.5 px-3 py-1 text-xs rounded border border-blue-600 text-blue-400 hover:bg-blue-600 hover:text-white transition-colors"
          >
            <Upload size={12} /> Import CSV
          </button>
        </header>

        <StatsPanel result={shownResult} error={tab === "results" ? error : null} />

        <div className="flex flex-wrap bg-slate-800 border-b border-slate-700 shrink-0">
          {tabs.map(({ key, label }) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={`relative px-3.5 py-2 text-sm transition-colors ${tab === key ? "text-blue-400" : "text-slate-400 hover:text-slate-200"}`}
            >
              {label}
              {tab === key && <motion.div layoutId="tab-ind" className="absolute bottom-0 left-0 right-0 h-0.5 bg-blue-500" />}
            </button>
          ))}
        </div>

        <div className="min-h-0 flex-1 overflow-hidden relative">
          <AnimatePresence mode="wait">
            <motion.div
              key={tab}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.18 }}
              className="absolute inset-0 overflow-auto"
            >
              {tab === "datos" && <DataLoader tables={tables} onChanged={refresh} />}
              {tab === "visual" && (
                <div className="min-h-full">
                  <ImageSearchPanel
                    tables={tables}
                    loading={tablesLoading}
                    onSearchResult={handleVisualResult}
                    onSqlGenerated={setSql}
                    onRefreshTables={refresh}
                  />
                  <div className="border-t border-slate-700">
                    <ProductResultsGrid rows={visualResult?.rows ?? []} imageColumn={visualImageColumn} />
                  </div>
                </div>
              )}
              {tab === "musical" && <MusicSearch tables={tables} />}
              {tab === "experimentos" && <ExperimentRunner tables={tables} />}
              {tab === "results" && <ResultsTable columns={result?.columns ?? []} rows={result?.rows ?? []} />}
              {tab === "history" && <MetricsHistory />}
            </motion.div>
          </AnimatePresence>
        </div>

        <div
          className="terminal-resizer shrink-0"
          role="separator"
          aria-orientation="horizontal"
          aria-label="Resize SQL terminal"
          onPointerDown={startTerminalResize}
          onPointerMove={resizeTerminal}
          onPointerUp={stopTerminalResize}
          onPointerCancel={stopTerminalResize}
        />

        <div
          className="shrink-0 border-t border-slate-700 bg-slate-800 flex flex-col"
          style={termOpen ? { height: terminalHeight } : undefined}
        >
          <div className="flex items-center px-3 py-1.5 border-b border-slate-700/60">
            <button
              onClick={() => setTermOpen((open) => !open)}
              className="flex items-center gap-1.5 text-xs font-semibold text-slate-300 hover:text-white"
            >
              <Terminal size={13} className="text-blue-500" /> Terminal SQL
              <ChevronDown size={13} className={`transition-transform ${termOpen ? "" : "-rotate-90"}`} />
            </button>
            <div className="flex gap-1 ml-3 flex-wrap">
              {EXAMPLE_QUERIES.map((query, i) => (
                <button
                  key={i}
                  onClick={() => { setSql(query); setTermOpen(true); }}
                  title={query}
                  className="px-2 py-0.5 text-[11px] rounded border border-slate-600 text-slate-400 hover:text-slate-100 hover:border-slate-400"
                >
                  Ej {i + 1}
                </button>
              ))}
            </div>
          </div>
          {termOpen && <SqlEditor value={sql} onChange={setSql} onRun={runQuery} loading={loading} />}
        </div>
      </main>
    </div>
  );
}
