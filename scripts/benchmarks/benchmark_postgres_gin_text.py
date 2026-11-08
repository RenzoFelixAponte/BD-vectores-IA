from pathlib import Path
import csv
import time
import statistics
import psycopg2
from psycopg2.extras import execute_values

ROOT_DIR = Path(__file__).resolve().parents[2]
CSV_PATH = ROOT_DIR / "datasets" / "fashion-ecommerce-500" / "products.csv"
RESULTS_DIR = ROOT_DIR / "scripts" / "benchmarks" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

RESULTS_CSV = RESULTS_DIR / "benchmark_postgres_gin_text_results.csv"
PLAN_TXT = RESULTS_DIR / "postgres_gin_text_explain.txt"

PG_CONFIG = {
    "host": "127.0.0.1",
    "port": 5432,
    "dbname": "postgres",
    "user": "postgres",
    "password": "postgres",
}

TABLE = "pg_products_text"
REPEATS = 30

TEST_CASES = [
    {"name": "buscar_kurta", "query": "kurta"},
    {"name": "buscar_body_lotion", "query": "body lotion"},
    {"name": "buscar_flip_flops", "query": "flip flops"},
]


def connect():
    return psycopg2.connect(**PG_CONFIG)


def load_products(conn):
    print("Preparando tabla PostgreSQL con índice GIN...")

    with conn.cursor() as cur:
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
                documento TEXT
            );
        """)

    rows = []
    with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            documento = " ".join([
                r.get("name", ""),
                r.get("gender", ""),
                r.get("category", ""),
                r.get("subcategory", ""),
                r.get("article_type", ""),
                r.get("color", ""),
                r.get("season", ""),
                r.get("usage", ""),
            ])

            rows.append((
                int(r["id"]),
                r.get("name", ""),
                r.get("gender", ""),
                r.get("category", ""),
                r.get("subcategory", ""),
                r.get("article_type", ""),
                r.get("color", ""),
                r.get("season", ""),
                r.get("usage", ""),
                r.get("image_path", ""),
                documento,
            ))

    with conn.cursor() as cur:
        execute_values(
            cur,
            f"""
            INSERT INTO {TABLE}
            (id, name, gender, category, subcategory, article_type, color, season, usage, image_path, documento)
            VALUES %s
            """,
            rows,
        )

        cur.execute(f"""
            CREATE INDEX idx_{TABLE}_gin
            ON {TABLE}
            USING GIN (to_tsvector('english', documento));
        """)

        cur.execute(f"ANALYZE {TABLE};")

    conn.commit()
    print(f"PostgreSQL listo: {TABLE} cargada con {len(rows)} filas e índice GIN.")


def run_query(conn, query):
    sql = f"""
        SELECT id, name, category, subcategory, article_type,
               ts_rank_cd(to_tsvector('english', documento), plainto_tsquery('english', %s)) AS rank
        FROM {TABLE}
        WHERE to_tsvector('english', documento) @@ plainto_tsquery('english', %s)
        ORDER BY rank DESC
        LIMIT 10;
    """

    started = time.perf_counter()
    with conn.cursor() as cur:
        cur.execute(sql, (query, query))
        rows = cur.fetchall()
    elapsed_ms = (time.perf_counter() - started) * 1000

    return elapsed_ms, len(rows)


def save_explain(conn):
    with open(PLAN_TXT, "w", encoding="utf-8") as out:
        for case in TEST_CASES:
            query = case["query"]
            out.write(f"\n\n=== EXPLAIN ANALYZE: {case['name']} ({query}) ===\n")

            explain_sql = f"""
                EXPLAIN (ANALYZE, BUFFERS)
                SELECT id, name
                FROM {TABLE}
                WHERE to_tsvector('english', documento) @@ plainto_tsquery('english', %s)
                LIMIT 10;
            """

            with conn.cursor() as cur:
                cur.execute(explain_sql, (query,))
                plan_rows = cur.fetchall()

            for row in plan_rows:
                out.write(row[0] + "\n")

    print(f"Plan EXPLAIN guardado en: {PLAN_TXT}")


def main():
    conn = connect()

    try:
        load_products(conn)

        results = []

        for case in TEST_CASES:
            print(f"\nEjecutando caso: {case['name']}")

            for i in range(REPEATS):
                elapsed_ms, row_count = run_query(conn, case["query"])

                results.append({
                    "case": case["name"],
                    "engine": "postgres_gin",
                    "query": case["query"],
                    "iteration": i + 1,
                    "client_time_ms": round(elapsed_ms, 4),
                    "row_count": row_count,
                })

        with open(RESULTS_CSV, "w", newline="", encoding="utf-8") as f:
            fieldnames = ["case", "engine", "query", "iteration", "client_time_ms", "row_count"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)

        save_explain(conn)

        print(f"\nResultados guardados en: {RESULTS_CSV}")

        print("\nResumen:")
        print("-" * 80)

        grouped = {}
        for r in results:
            grouped.setdefault(r["case"], []).append(float(r["client_time_ms"]))

        for case, times in grouped.items():
            print(
                f"{case:22s} | postgres_gin | "
                f"avg={statistics.mean(times):8.4f} ms | "
                f"median={statistics.median(times):8.4f} ms | "
                f"min={min(times):8.4f} ms | "
                f"max={max(times):8.4f} ms"
            )

    finally:
        conn.close()


if __name__ == "__main__":
    main()