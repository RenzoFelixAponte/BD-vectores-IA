import { motion } from "framer-motion";
import { PackageSearch } from "lucide-react";
import { ProductImage } from "./ProductImage";

interface Props {
  rows: Record<string, unknown>[];
  imageColumn: string | null;
}

function pickTitle(row: Record<string, unknown>) {
  for (const key of ["product_name", "name", "title", "nombre", "description"]) {
    const value = row[key];
    if (typeof value === "string" && value.trim()) return value;
  }
  return `Product ${String(row.id ?? row.ID ?? "")}`.trim();
}

function formatScore(value: unknown) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "-";
  return n.toFixed(4);
}

export function ProductResultsGrid({ rows, imageColumn }: Props) {
  if (!rows.length) {
    return (
      <div className="flex min-h-[260px] items-center justify-center text-slate-500 text-sm">
        <div className="flex flex-col items-center gap-2">
          <PackageSearch size={32} />
          <span>No visual search results yet.</span>
        </div>
      </div>
    );
  }

  return (
    <div className="p-4">
      <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(190px, 1fr))" }}>
        {rows.map((row, index) => {
          const title = pickTitle(row);
          return (
            <motion.article
              key={`${String(row.id ?? row.ID ?? index)}-${index}`}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.16, delay: Math.min(index * 0.025, 0.2) }}
              className="overflow-hidden rounded border border-slate-700 bg-slate-900"
            >
              <ProductImage
                path={imageColumn ? row[imageColumn] : undefined}
                alt={title}
                className="aspect-square w-full"
              />
              <div className="space-y-1.5 p-3">
                <div className="truncate text-sm font-semibold text-slate-100" title={title}>
                  {title}
                </div>
                <div className="flex items-center justify-between gap-2 text-xs">
                  <span className="text-slate-500">Score</span>
                  <span className="font-mono text-emerald-400">{formatScore(row._score)}</span>
                </div>
                <div className="truncate text-[11px] text-slate-500">
                  ID {String(row.id ?? row.ID ?? "-")}
                </div>
              </div>
            </motion.article>
          );
        })}
      </div>
    </div>
  );
}
