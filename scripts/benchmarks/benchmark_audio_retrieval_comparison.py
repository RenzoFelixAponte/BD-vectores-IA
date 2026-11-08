from pathlib import Path
from contextlib import contextmanager
from collections import defaultdict
import csv
import json
import os
import statistics
import time

import pg8000.dbapi


ROOT_DIR = Path(__file__).resolve().parents[2]
MEDIA_DIR = Path(os.getenv("AUDIO_MEDIA_DIR", ROOT_DIR / "back" / "data" / "media" / "cancion"))
INDEX_PATH = Path(os.getenv(
    "AUDIO_INDEX_PATH",
    ROOT_DIR / "back" / "data" / "cancion_ix_pista" / "histogram_index.json",
))
RESULTS_DIR = ROOT_DIR / "scripts" / "benchmarks" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

DATASET_NAME = os.getenv("DATASET_NAME", "cancion_audio")

PG_CONFIG = {
    "host": os.getenv("PGHOST", "127.0.0.1"),
    "port": int(os.getenv("PGPORT", "5432")),
    "database": os.getenv("PGDATABASE", "postgres"),
    "user": os.getenv("PGUSER", "postgres"),
    "password": os.getenv("PGPASSWORD", "postgres"),
}

TABLE = os.getenv("PGVECTOR_AUDIO_TABLE", "pg_cancion_audio_vectors_cmp")
REPEATS = int(os.getenv("REPEATS", "30"))
TOP_K = int(os.getenv("TOP_K", "10"))
FORCE_VECTOR_INDEX = os.getenv("PGVECTOR_FORCE_INDEX", "0").lower() in {"1", "true", "yes"}
PLAN_MODE = "forced_index" if FORCE_VECTOR_INDEX else "natural"
RESULTS_CSV = RESULTS_DIR / f"benchmark_audio_retrieval_comparison_{DATASET_NAME}_{PLAN_MODE}.csv"
PLAN_TXT = RESULTS_DIR / f"benchmark_audio_retrieval_comparison_{DATASET_NAME}_{PLAN_MODE}_explain.txt"

TEST_CASES = [
    {"name": "buscar_blues", "genre": "blues"},
    {"name": "buscar_classical", "genre": "classical"},
    {"name": "buscar_rock", "genre": "rock"},
]


def connect():
    return pg8000.dbapi.connect(**PG_CONFIG)


@contextmanager
def db_cursor(conn):
    cur = conn.cursor()
    try:
        yield cur
    finally:
        cur.close()


def vector_literal(values):
    return "[" + ",".join(f"{float(v):.8g}" for v in values) + "]"


def l2_norm(sparse):
    return sum(v * v for v in sparse.values()) ** 0.5


def load_audio_metadata():
    metadata = {}
    doc_id = 1
    for genre_dir in sorted(path for path in MEDIA_DIR.iterdir() if path.is_dir()):
        for audio_file in sorted(genre_dir.glob("*.wav")):
            metadata[doc_id] = {
                "genre": genre_dir.name,
                "path": str(audio_file),
                "track": f"{genre_dir.name}/{audio_file.name}",
            }
            doc_id += 1
    return metadata


def load_histograms():
    payload = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    postings = {
        int(word_id): [(int(doc_id), float(weight)) for doc_id, weight in entries]
        for word_id, entries in payload["postings"].items()
    }
    dimension = max(postings) + 1
    sparse_by_doc = defaultdict(dict)
    for word_id, entries in postings.items():
        for doc_id, weight in entries:
            sparse_by_doc[doc_id][word_id] = weight
    sparse_by_doc = {doc_id: dict(sparse) for doc_id, sparse in sparse_by_doc.items()}
    norms = {doc_id: l2_norm(sparse) for doc_id, sparse in sparse_by_doc.items()}
    return postings, sparse_by_doc, norms, dimension


def dense_vector(sparse, dimension):
    values = [0.0] * dimension
    for word_id, weight in sparse.items():
        values[word_id] = weight
    return values


def select_test_cases(metadata, sparse_by_doc):
    selected = []
    for case in TEST_CASES:
        found = None
        for doc_id in sorted(sparse_by_doc):
            row = metadata.get(doc_id)
            if row and row["genre"] == case["genre"]:
                found = doc_id
                break
        if found is None:
            raise RuntimeError(f"No se encontro audio indexado para el caso '{case['name']}'")
        selected.append({
            **case,
            "query_doc_id": found,
            "query_label": metadata[found]["track"],
            "query_sparse": sparse_by_doc[found],
        })
    return selected


def own_index_knn(query_sparse, postings, norms, k):
    started = time.perf_counter()
    dots = defaultdict(float)
    for word_id, q_weight in query_sparse.items():
        for doc_id, d_weight in postings.get(word_id, []):
            dots[doc_id] += q_weight * d_weight
    q_norm = l2_norm(query_sparse)
    scored = []
    for doc_id, dot in dots.items():
        denom = q_norm * norms.get(doc_id, 0.0)
        scored.append((doc_id, dot / denom if denom > 0 else 0.0))
    scored.sort(key=lambda item: (item[1], -item[0]), reverse=True)
    elapsed_ms = (time.perf_counter() - started) * 1000
    return scored[:k], elapsed_ms


def own_sequential_knn(query_sparse, sparse_by_doc, norms, k):
    started = time.perf_counter()
    q_norm = l2_norm(query_sparse)
    scored = []
    for doc_id, sparse in sparse_by_doc.items():
        if len(query_sparse) < len(sparse):
            dot = sum(weight * sparse.get(word_id, 0.0) for word_id, weight in query_sparse.items())
        else:
            dot = sum(weight * query_sparse.get(word_id, 0.0) for word_id, weight in sparse.items())
        denom = q_norm * norms.get(doc_id, 0.0)
        scored.append((doc_id, dot / denom if denom > 0 else 0.0))
    scored.sort(key=lambda item: (item[1], -item[0]), reverse=True)
    elapsed_ms = (time.perf_counter() - started) * 1000
    return scored[:k], elapsed_ms


def create_pgvector_table(conn, metadata, sparse_by_doc, dimension):
    print("Preparando tabla PostgreSQL con pgvector para audio...")
    with db_cursor(conn) as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        cur.execute(f"DROP TABLE IF EXISTS {TABLE};")
        cur.execute(f"""
            CREATE TABLE {TABLE} (
                id INT PRIMARY KEY,
                genre TEXT,
                track TEXT,
                path TEXT,
                embedding vector({dimension})
            );
        """)
    conn.commit()

    rows = []
    for doc_id, sparse in sorted(sparse_by_doc.items()):
        row = metadata.get(doc_id)
        if not row:
            continue
        rows.append((doc_id, row["genre"], row["track"], row["path"], vector_literal(dense_vector(sparse, dimension))))

    with db_cursor(conn) as cur:
        cur.executemany(
            f"""
            INSERT INTO {TABLE}
            (id, genre, track, path, embedding)
            VALUES (%s,%s,%s,%s,%s::vector)
            """,
            rows,
        )
        cur.execute(f"""
            CREATE INDEX idx_{TABLE}_hnsw
            ON {TABLE}
            USING hnsw (embedding vector_cosine_ops);
        """)
        cur.execute(f"ANALYZE {TABLE};")
    conn.commit()
    return len(rows)


def pgvector_knn(conn, query_sparse, dimension, k):
    query = vector_literal(dense_vector(query_sparse, dimension))
    sql = f"""
        SELECT id, 1 - (embedding <=> %s::vector) AS score
        FROM {TABLE}
        ORDER BY embedding <=> %s::vector
        LIMIT {k};
    """
    started = time.perf_counter()
    with db_cursor(conn) as cur:
        if FORCE_VECTOR_INDEX:
            cur.execute("SET LOCAL enable_seqscan = off;")
        cur.execute(sql, (query, query))
        rows = [(int(doc_id), float(score)) for doc_id, score in cur.fetchall()]
    elapsed_ms = (time.perf_counter() - started) * 1000
    return rows, elapsed_ms


def pg_sizes(conn):
    with db_cursor(conn) as cur:
        cur.execute(f"""
            SELECT
                pg_relation_size('{TABLE}'::regclass),
                pg_indexes_size('{TABLE}'::regclass),
                pg_total_relation_size('{TABLE}'::regclass);
        """)
        return tuple(int(v) for v in cur.fetchone())


def explain_plan(conn, case, dimension):
    query = vector_literal(dense_vector(case["query_sparse"], dimension))
    with db_cursor(conn) as cur:
        if FORCE_VECTOR_INDEX:
            cur.execute("SET LOCAL enable_seqscan = off;")
        cur.execute(
            f"""
            EXPLAIN (ANALYZE, BUFFERS)
            SELECT id, track
            FROM {TABLE}
            ORDER BY embedding <=> %s::vector
            LIMIT {TOP_K};
            """,
            (query,),
        )
        lines = [row[0] for row in cur.fetchall()]
    text = "\n".join(lines)
    if "Index Scan" in text:
        plan_node = "Index Scan"
    elif "Seq Scan" in text:
        plan_node = "Seq Scan"
    else:
        plan_node = "Other"
    return lines, plan_node, "idx_" in text.lower() or "hnsw" in text.lower()


def recall_at_k(actual, reference):
    if not reference:
        return 0.0
    actual_ids = {doc_id for doc_id, _ in actual}
    reference_ids = {doc_id for doc_id, _ in reference}
    return len(actual_ids & reference_ids) / min(len(reference_ids), TOP_K)


def append_result(results, case, engine, iteration, elapsed_ms, rows, reference, metadata):
    results.append({
        **metadata,
        "case": case["name"],
        "query_genre": case["genre"],
        "query_doc_id": case["query_doc_id"],
        "engine": engine,
        "iteration": iteration,
        "client_time_ms": round(elapsed_ms, 4),
        "row_count": len(rows),
        "recall_at_k_vs_own_index": round(recall_at_k(rows, reference), 4),
        "top_ids": " ".join(str(doc_id) for doc_id, _ in rows),
    })


def main():
    metadata = load_audio_metadata()
    postings, sparse_by_doc, norms, dimension = load_histograms()
    test_cases = select_test_cases(metadata, sparse_by_doc)
    own_index_bytes = INDEX_PATH.stat().st_size

    conn = connect()
    try:
        dataset_size = create_pgvector_table(conn, metadata, sparse_by_doc, dimension)
        table_bytes, pg_index_bytes, total_bytes = pg_sizes(conn)

        plan_by_case = {}
        with open(PLAN_TXT, "w", encoding="utf-8") as out:
            for case in test_cases:
                lines, plan_node, uses_index = explain_plan(conn, case, dimension)
                plan_by_case[case["name"]] = (plan_node, uses_index)
                out.write(f"\n\n=== {case['name']} ({case['query_label']}) ===\n")
                out.write("\n".join(lines))

        metadata_base = {
            "modality": "audio",
            "dataset_name": DATASET_NAME,
            "dataset_size": dataset_size,
            "vector_dimension": dimension,
            "top_k": TOP_K,
            "repeats": REPEATS,
            "own_index_bytes": own_index_bytes,
            "pg_table_bytes": table_bytes,
            "pg_index_bytes": pg_index_bytes,
            "pg_total_bytes": total_bytes,
        }

        results = []
        for case in test_cases:
            print(f"\nCaso audio: {case['name']} ({case['query_label']})")
            reference, _ = own_index_knn(case["query_sparse"], postings, norms, TOP_K)
            plan_node, uses_index = plan_by_case[case["name"]]

            for i in range(1, REPEATS + 1):
                rows, elapsed = own_index_knn(case["query_sparse"], postings, norms, TOP_K)
                append_result(results, case, "own_histogram_inverted_index", i, elapsed, rows, reference, {
                    **metadata_base,
                    "pg_plan_node": "",
                    "pg_uses_vector_index": "",
                })

                rows, elapsed = own_sequential_knn(case["query_sparse"], sparse_by_doc, norms, TOP_K)
                append_result(results, case, "own_histogram_sequential", i, elapsed, rows, reference, {
                    **metadata_base,
                    "pg_plan_node": "",
                    "pg_uses_vector_index": "",
                })

                rows, elapsed = pgvector_knn(conn, case["query_sparse"], dimension, TOP_K)
                append_result(results, case, "postgres_pgvector_hnsw", i, elapsed, rows, reference, {
                    **metadata_base,
                    "pg_plan_node": plan_node,
                    "pg_uses_vector_index": uses_index,
                })

        fieldnames = list(results[0].keys())
        with open(RESULTS_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)

        print(f"\nResultados guardados en: {RESULTS_CSV}")
        print(f"Planes guardados en: {PLAN_TXT}")
        print("\nResumen promedio por motor:")
        grouped = defaultdict(list)
        for row in results:
            grouped[row["engine"]].append(float(row["client_time_ms"]))
        for engine, times in grouped.items():
            print(f"{engine:32s} avg={statistics.mean(times):8.4f} ms median={statistics.median(times):8.4f} ms")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
