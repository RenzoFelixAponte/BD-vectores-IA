import { motion } from "framer-motion";
import { ImagePlus, Play, Search, UploadCloud } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import type { QueryResult, TableInfo } from "../types/api";
import { ProductImage } from "./ProductImage";

type Method = "MULTIMEDIA" | "SEQUENTIAL";

interface Props {
  tables: TableInfo[];
  loading: boolean;
  onSearchResult: (result: QueryResult | null, imageColumn: string | null) => void;
  onSqlGenerated: (sql: string) => void;
  onRefreshTables: () => Promise<void> | void;
}

function imageColumns(table: TableInfo | undefined) {
  return table?.columns.filter((column) => column.type.toUpperCase() === "IMAGE") ?? [];
}

function hasMultimediaIndex(table: TableInfo | undefined, imageColumn: string) {
  return !!table?.content_indexes?.some(
    (index) => index.type === "multimedia" && index.columns.includes(imageColumn)
  );
}

export function ImageSearchPanel({ tables, loading, onSearchResult, onSqlGenerated, onRefreshTables }: Props) {
  const productTables = useMemo(
    () => tables.filter((table) => imageColumns(table).length > 0),
    [tables]
  );
  const [tableName, setTableName] = useState(productTables[0]?.name ?? "");
  const selectedTable = productTables.find((table) => table.name === tableName) ?? productTables[0];
  const columns = imageColumns(selectedTable);
  const [imageColumn, setImageColumn] = useState(columns[0]?.name ?? "");
  const effectiveColumn = columns.some((column) => column.name === imageColumn) ? imageColumn : columns[0]?.name ?? "";
  const [queryPath, setQueryPath] = useState("");
  const [method, setMethod] = useState<Method>("MULTIMEDIA");
  const [k, setK] = useState(10);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const indexed = hasMultimediaIndex(selectedTable, effectiveColumn);

  function buildSql(nextMethod = method) {
    const safePath = queryPath.replace(/'/g, "''");
    return `SELECT * FROM ${selectedTable?.name ?? ""} WHERE ${effectiveColumn} <-> '${safePath}' LIMIT ${k} USING ${nextMethod};`;
  }

  async function runSearch(nextMethod = method) {
    if (!selectedTable || !effectiveColumn || !queryPath.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api.visualSearch({
        table: selectedTable.name,
        imageColumn: effectiveColumn,
        queryPath,
        k,
        method: nextMethod,
      });
      onSqlGenerated(buildSql(nextMethod));
      onSearchResult(result, effectiveColumn);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      onSearchResult(null, effectiveColumn);
    } finally {
      setBusy(false);
    }
  }

  async function createIndex() {
    if (!selectedTable || !effectiveColumn) return;
    const sql = `CREATE INDEX idx_${selectedTable.name}_${effectiveColumn}_img ON ${selectedTable.name} (${effectiveColumn}) USING MULTIMEDIA;`;
    setBusy(true);
    setError(null);
    try {
      await api.executeQuery(sql);
      onSqlGenerated(sql);
      await onRefreshTables();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function uploadImage(file: File) {
    setBusy(true);
    setError(null);
    try {
      const uploaded = await api.uploadQueryImage(file);
      setQueryPath(uploaded.path);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  if (!productTables.length) {
    return (
      <div className="flex min-h-[320px] items-center justify-center p-8 text-center text-slate-500">
        <div className="max-w-md space-y-3">
          <ImagePlus size={36} className="mx-auto" />
          <p className="text-sm text-slate-300">No IMAGE product table found.</p>
          <p className="text-xs">Import a product CSV and mark its image path column as IMAGE.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="border-b border-slate-700 bg-slate-900">
      <div className="grid gap-4 p-4 lg:grid-cols-[320px_1fr]">
        <section className="rounded border border-slate-700 bg-slate-800">
          <div className="border-b border-slate-700 px-4 py-3">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-100">
              <Search size={16} className="text-cyan-400" />
              Visual Search
            </div>
          </div>
          <div className="space-y-3 p-4">
            <label className="block">
              <span className="mb-1 block text-xs font-semibold uppercase tracking-wider text-slate-500">Products</span>
              <select
                value={selectedTable?.name ?? ""}
                onChange={(event) => {
                  const nextName = event.target.value;
                  const nextTable = productTables.find((table) => table.name === nextName);
                  setTableName(nextName);
                  setImageColumn(imageColumns(nextTable)[0]?.name ?? "");
                }}
                className="w-full rounded border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-slate-100 focus:border-cyan-500 focus:outline-none"
              >
                {productTables.map((table) => <option key={table.name} value={table.name}>{table.name}</option>)}
              </select>
            </label>

            <label className="block">
              <span className="mb-1 block text-xs font-semibold uppercase tracking-wider text-slate-500">Image Column</span>
              <select
                value={effectiveColumn}
                onChange={(event) => setImageColumn(event.target.value)}
                className="w-full rounded border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-slate-100 focus:border-cyan-500 focus:outline-none"
              >
                {columns.map((column) => <option key={column.name} value={column.name}>{column.name}</option>)}
              </select>
            </label>

            <div className="grid grid-cols-2 gap-2">
              <label className="block">
                <span className="mb-1 block text-xs font-semibold uppercase tracking-wider text-slate-500">Method</span>
                <select
                  value={method}
                  onChange={(event) => setMethod(event.target.value as Method)}
                  className="w-full rounded border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-slate-100 focus:border-cyan-500 focus:outline-none"
                >
                  <option value="MULTIMEDIA">Indexed</option>
                  <option value="SEQUENTIAL">Sequential</option>
                </select>
              </label>
              <label className="block">
                <span className="mb-1 block text-xs font-semibold uppercase tracking-wider text-slate-500">Top K</span>
                <input
                  type="number"
                  min={1}
                  max={50}
                  value={k}
                  onChange={(event) => setK(Math.max(1, Math.min(50, Number(event.target.value) || 1)))}
                  className="w-full rounded border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-slate-100 focus:border-cyan-500 focus:outline-none"
                />
              </label>
            </div>

            <label className="block">
              <span className="mb-1 block text-xs font-semibold uppercase tracking-wider text-slate-500">Query Image Path</span>
              <input
                value={queryPath}
                onChange={(event) => setQueryPath(event.target.value)}
                placeholder="datasets/query/shirt.jpg"
                className="w-full rounded border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-600 focus:border-cyan-500 focus:outline-none"
              />
            </label>

            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={busy}
                className="flex items-center justify-center gap-2 rounded border border-slate-600 px-3 py-2 text-sm text-slate-300 transition-colors hover:border-cyan-500 hover:text-cyan-300 disabled:opacity-50"
              >
                <UploadCloud size={15} /> Upload
              </button>
              <button
                type="button"
                onClick={() => void runSearch()}
                disabled={busy || !queryPath.trim() || !effectiveColumn || (method === "MULTIMEDIA" && !indexed)}
                className="flex items-center justify-center gap-2 rounded bg-cyan-600 px-3 py-2 text-sm font-semibold text-white transition-colors hover:bg-cyan-500 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {busy ? <span className="spinner" /> : <Play size={14} fill="currentColor" />} Search
              </button>
            </div>

            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void uploadImage(file);
              }}
            />

            {!indexed && (
              <button
                type="button"
                onClick={() => void createIndex()}
                disabled={busy || !effectiveColumn}
                className="w-full rounded border border-amber-700 bg-amber-950/30 px-3 py-2 text-sm text-amber-300 transition-colors hover:border-amber-500 disabled:opacity-50"
              >
                Build image index
              </button>
            )}

            {error && (
              <pre className="whitespace-pre-wrap rounded border border-red-800/60 bg-red-950/30 px-3 py-2 text-xs text-red-300">
                {error}
              </pre>
            )}
          </div>
        </section>

        <section className="min-h-[280px] overflow-hidden rounded border border-slate-700 bg-slate-800">
          <div className="border-b border-slate-700 px-4 py-3">
            <div className="text-sm font-semibold text-slate-100">Query Preview</div>
          </div>
          <div className="grid gap-4 p-4 md:grid-cols-[240px_minmax(0,1fr)]">
            <ProductImage path={queryPath} alt="Query" className="aspect-square w-full rounded border border-slate-700" />
            <div className="min-w-0 space-y-3 text-sm text-slate-300">
              <div className="grid grid-cols-2 gap-2 text-xs">
                <span className="text-slate-500">Table</span>
                <span className="truncate text-slate-200">{selectedTable?.name}</span>
                <span className="text-slate-500">Column</span>
                <span className="truncate text-slate-200">{effectiveColumn}</span>
                <span className="text-slate-500">Index</span>
                <span className={indexed ? "text-emerald-400" : "text-amber-400"}>
                  {indexed ? "Ready" : "Missing"}
                </span>
              </div>
              <motion.pre
                key={buildSql()}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="max-h-32 overflow-auto whitespace-pre-wrap break-all rounded bg-slate-950 p-3 text-xs text-slate-400"
              >
                {buildSql()}
              </motion.pre>
              {loading && <p className="text-xs text-slate-500">Refreshing product tables...</p>}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
