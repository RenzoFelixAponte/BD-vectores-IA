import type {
  ExperimentResponse,
  FsResponse,
  MetricsEntry,
  QueryResult,
  RTreePointsResponse,
  SearchResponse,
  TableListResponse,
} from "../types/api";

// Única fuente de la dirección del backend: frontend/.env (VITE_API_URL).
// El .env guarda solo el destino (http://host:puerto); aquí se agrega el subpath.
const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const BASE = `${API_URL}/api/v1`;

async function request<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail = body?.detail ?? body;
    const msg =
      typeof detail === "object"
        ? detail?.message ?? JSON.stringify(detail)
        : String(detail);
    throw new Error(msg || `HTTP ${res.status}`);
  }

  return res.json() as Promise<T>;
}

export const api = {
  executeQuery: (sql: string) =>
    request<QueryResult>("/query", {
      method: "POST",
      body: JSON.stringify({ sql }),
    }),

  listTables: () => request<TableListResponse>("/tables"),

  dropTable: (name: string) =>
    request<{ message: string; table: string }>(`/tables/${name}`, {
      method: "DELETE",
    }),

  getRTreePoints: (table: string) =>
    request<RTreePointsResponse>(`/indexes/${table}/points`),

  getMetricsHistory: (limit = 50) =>
    request<{ entries: MetricsEntry[]; count: number }>(
      `/metrics/history?limit=${limit}`
    ),

  clearMetrics: () =>
    request<{ message: string }>("/metrics", { method: "DELETE" }),

  // ---- Recuperación multimodal (Proyecto 2) ----

  browseFs: (path = "") =>
    request<FsResponse>(`/fs?path=${encodeURIComponent(path)}`),

  loadFolder: (body: {
    table: string;
    folder: string;
    mapping: Record<string, string>;
    limit_per_subfolder?: number | null;
    copy?: boolean;
  }) =>
    request<{ table: string; inserted: number; copied: boolean; media_dir: string | null }>("/datasets/load-folder", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  searchText: (body: {
    table: string;
    column: string;
    query: string;
    k?: number;
    method?: string | null;
    genre?: string | null;
  }) =>
    request<SearchResponse>("/search/text", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  searchMedia: (
    file: File,
    opts: { table: string; column: string; k?: number; method?: string | null; genre?: string | null }
  ) => {
    const form = new FormData();
    form.append("file", file);
    form.append("table", opts.table);
    form.append("column", opts.column);
    form.append("k", String(opts.k ?? 10));
    if (opts.method) form.append("method", opts.method);
    if (opts.genre) form.append("genre", opts.genre);
    return fetch(`${BASE}/search/media`, { method: "POST", body: form }).then(
      async (res) => {
        if (!res.ok) throw new Error((await res.json().catch(() => ({})))?.detail ?? `HTTP ${res.status}`);
        return res.json() as Promise<SearchResponse>;
      }
    );
  },

  mediaUrl: (path: string) => `${BASE}/media?path=${encodeURIComponent(path)}`,

  uploadQueryImage: async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${BASE}/media/query-image`, {
      method: "POST",
      body: form,
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(String(body?.detail ?? `HTTP ${res.status}`));
    }
    return res.json() as Promise<{ path: string }>;
  },

  imageUrl: (path: unknown) =>
    `${BASE}/media/image?path=${encodeURIComponent(String(path ?? ""))}`,

  visualSearch: (params: {
    table: string;
    imageColumn: string;
    queryPath: string;
    k: number;
    method: "MULTIMEDIA" | "SEQUENTIAL";
  }) => {
    const escapedPath = params.queryPath.replace(/'/g, "''");
    const sql = `SELECT * FROM ${params.table} WHERE ${params.imageColumn} <-> '${escapedPath}' LIMIT ${params.k} USING ${params.method};`;
    return api.executeQuery(sql);
  },

  runExperiment: (body: {
    table: string;
    column: string;
    kind: string;
    engines: string[];
    top_k: number;
    queries: number;
    repeats: number;
  }) =>
    request<ExperimentResponse>("/experiments/run", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};
