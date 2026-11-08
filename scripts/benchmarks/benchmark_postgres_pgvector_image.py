from pathlib import Path
from contextlib import contextmanager
import csv
import json
import os
import statistics
import time

import pg8000.dbapi

ROOT_DIR = Path(__file__).resolve().parents[2]
CSV_PATH = ROOT_DIR / "datasets" / "fashion-ecommerce-500" / "products.csv"
INDEX_PATH = ROOT_DIR / "back" / "data" / "products_idx_products_image" / "histogram_index.json"
RESULTS_DIR = ROOT_DIR / "scripts" / "benchmarks" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

RESULTS_CSV = RESULTS_DIR / "benchmark_postgres_pgvector_image_results.csv"
PLAN_TXT = RESULTS_DIR / "postgres_pgvector_image_explain.txt"

PG_CONFIG = {
    "host": os.getenv("PGHOST", "127.0.0.1"),
    "port": int(os.getenv("PGPORT", "5432")),
    "database": os.getenv("PGDATABASE", "postgres"),
    "user": os.getenv("PGUSER", "postgres"),
    "password": os.getenv("PGPASSWORD", "postgres"),
}

TABLE = "pg_products_image_vectors"
REPEATS = 30
TOP_K = 10

TEST_CASES = [
    {"name": "buscar_kurta", "query": "kurta"},
    {"name": "buscar_body_lotion", "query": "body lotion"},
    {"name": "buscar_flip_flops", "query": "flip flops"},
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


def document_text(row):
    fields = [
        "name",
        "gender",
        "category",
        "subcategory",
        "article_type",
        "color",
        "season",
        "usage",
    ]
    return " ".join(row.get(field, "") for field in fields).lower()


def load_products_metadata():
    products = {}
    with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            product_id = int(row["id"])
            products[product_id] = row
    return products


def load_histograms():
    """Reconstruye {doc_id: vector denso} desde postings del indice multimedia."""
    payload = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    postings = payload["postings"]
    dimension = max(int(word_id) for word_id in postings) + 1

    histograms = {}
    for word_id_text, entries in postings.items():
        word_id = int(word_id_text)
        for doc_id, weight in entries:
            doc_id = int(doc_id)
            if doc_id not in histograms:
                histograms[doc_id] = [0.0] * dimension
            histograms[doc_id][word_id] = float(weight)

    return histograms, dimension


def select_test_cases(products, histograms):
    selected = []
    for case in TEST_CASES:
        terms = case["query"].lower().split()
        found = None
        for product_id in sorted(histograms):
            row = products.get(product_id)
            if not row:
                continue
            text = document_text(row)
            if all(term in text for term in terms):
                found = product_id
                break
        if found is None:
            raise RuntimeError(f"No se encontro producto indexado para el caso '{case['name']}'")
        row = products[found]
        selected.append({
            **case,
            "query_doc_id": found,
            "query_label": row.get("name", ""),
            "query_vector": histograms[found],
        })
    return selected


def create_vector_index(conn):
    index_name = f"idx_{TABLE}_embedding"

    with db_cursor(conn) as cur:
        try:
            cur.execute(f"""
                CREATE INDEX {index_name}_hnsw
                ON {TABLE}
                USING hnsw (embedding vector_cosine_ops);
            """)
            conn.commit()
            return "postgres_pgvector_hnsw"
        except pg8000.dbapi.Error as exc:
            conn.rollback()
            print(f"No se pudo crear indice HNSW ({exc}).")
            print("Intentando con IVFFLAT...")

        cur.execute(f"""
            CREATE INDEX {index_name}_ivfflat
            ON {TABLE}
            USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 20);
        """)
        conn.commit()
        return "postgres_pgvector_ivfflat"


def load_products(conn):
    print("Preparando tabla PostgreSQL con pgvector...")

    products = load_products_metadata()
    histograms, dimension = load_histograms()
    test_cases = select_test_cases(products, histograms)

    with db_cursor(conn) as cur:
        try:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        except pg8000.dbapi.Error as exc:
            raise RuntimeError(
                "No se pudo habilitar pgvector. Verifica que PostgreSQL tenga instalada "
                "la extension 'vector'."
            ) from exc

        cur.execute(f"DROP TABLE IF EXISTS {TABLE};")
        cur.execute(f"""
            CREATE TABLE {TABLE} (
                id INT PRIMARY KEY,
                name TEXT,
                gender TEXT,
                category TEXT,
                subcategory TEXT,
                article_type TEXT,
                color TEXT,
                season TEXT,
                usage TEXT,
                image_path TEXT,
                embedding vector({dimension})
            );
        """)

    rows = []
    for product_id, vector in sorted(histograms.items()):
        row = products.get(product_id)
        if not row:
            continue
        rows.append((
            product_id,
            row.get("name", ""),
            row.get("gender", ""),
            row.get("category", ""),
            row.get("subcategory", ""),
            row.get("article_type", ""),
            row.get("color", ""),
            row.get("season", ""),
            row.get("usage", ""),
            row.get("image_path", ""),
            vector_literal(vector),
        ))

    with db_cursor(conn) as cur:
        cur.executemany(
            f"""
            INSERT INTO {TABLE}
            (id, name, gender, category, subcategory, article_type, color, season, usage, image_path, embedding)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::vector)
            """,
            rows,
        )
        cur.execute(f"ANALYZE {TABLE};")
    conn.commit()

    engine = create_vector_index(conn)

    with db_cursor(conn) as cur:
        cur.execute(f"ANALYZE {TABLE};")
    conn.commit()

    print(
        f"PostgreSQL listo: {TABLE} cargada con {len(rows)} filas, "
        f"dimension={dimension}, indice={engine}."
    )
    return test_cases, engine


def run_query(conn, query_vector):
    sql = f"""
        SELECT id, name, category, subcategory, article_type,
               1 - (embedding <=> %s::vector) AS score
        FROM {TABLE}
        ORDER BY embedding <=> %s::vector
        LIMIT {TOP_K};
    """
    query = vector_literal(query_vector)

    started = time.perf_counter()
    with db_cursor(conn) as cur:
        cur.execute(sql, (query, query))
        rows = cur.fetchall()
    elapsed_ms = (time.perf_counter() - started) * 1000

    return elapsed_ms, len(rows)


def save_explain(conn, test_cases, engine):
    with open(PLAN_TXT, "w", encoding="utf-8") as out:
        out.write(f"Engine: {engine}\n")
        out.write(f"Table: {TABLE}\n")

        for case in test_cases:
            query = vector_literal(case["query_vector"])
            out.write(
                f"\n\n=== EXPLAIN ANALYZE: {case['name']} "
                f"(doc_id={case['query_doc_id']}, {case['query_label']}) ===\n"
            )

            explain_sql = f"""
                EXPLAIN (ANALYZE, BUFFERS)
                SELECT id, name
                FROM {TABLE}
                ORDER BY embedding <=> %s::vector
                LIMIT {TOP_K};
            """

            with db_cursor(conn) as cur:
                cur.execute(explain_sql, (query,))
                plan_rows = cur.fetchall()

            for row in plan_rows:
                out.write(row[0] + "\n")

    print(f"Plan EXPLAIN guardado en: {PLAN_TXT}")


def main():
    conn = connect()

    try:
        test_cases, engine = load_products(conn)
        results = []

        for case in test_cases:
            print(
                f"\nEjecutando caso: {case['name']} "
                f"(doc_id={case['query_doc_id']}, {case['query_label']})"
            )

            for i in range(REPEATS):
                elapsed_ms, row_count = run_query(conn, case["query_vector"])

                results.append({
                    "case": case["name"],
                    "engine": engine,
                    "query": case["query"],
                    "query_doc_id": case["query_doc_id"],
                    "iteration": i + 1,
                    "client_time_ms": round(elapsed_ms, 4),
                    "row_count": row_count,
                })

        with open(RESULTS_CSV, "w", newline="", encoding="utf-8") as f:
            fieldnames = [
                "case",
                "engine",
                "query",
                "query_doc_id",
                "iteration",
                "client_time_ms",
                "row_count",
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)

        save_explain(conn, test_cases, engine)

        print(f"\nResultados guardados en: {RESULTS_CSV}")
        print("\nResumen:")
        print("-" * 80)

        grouped = {}
        for r in results:
            grouped.setdefault(r["case"], []).append(float(r["client_time_ms"]))

        for case, times in grouped.items():
            print(
                f"{case:22s} | {engine:24s} | "
                f"avg={statistics.mean(times):8.4f} ms | "
                f"median={statistics.median(times):8.4f} ms | "
                f"min={min(times):8.4f} ms | "
                f"max={max(times):8.4f} ms"
            )

    finally:
        conn.close()


if __name__ == "__main__":
    main()
