from pathlib import Path
import csv
import json
import time
import statistics
import urllib.request
import urllib.error

import psycopg2

from benchmark_config import MINISGBD_URL, POSTGRES_CONFIG


ROOT_DIR = Path(__file__).resolve().parents[2]
CSV_PATH = ROOT_DIR / "lugares.csv"
RESULTS_DIR = Path(__file__).resolve().parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

MINI_TABLE = "lugares_test"
POSTGRES_TABLE = "bench_lugares"

REPEATS = 10


TEST_CASES = [
    {
    "name": "rango_id_1_10",
    "mini_sql": f"SELECT * FROM {MINI_TABLE} WHERE id BETWEEN 1 AND 10;",
    "pg_sql": f"SELECT * FROM {POSTGRES_TABLE} WHERE id BETWEEN 1 AND 10;",
    },
    {
        "name": "buscar_id_1",
        "mini_sql": f"SELECT * FROM {MINI_TABLE} WHERE id = 1;",
        "pg_sql": f"SELECT * FROM {POSTGRES_TABLE} WHERE id = 1;",
    },
    {
        "name": "buscar_id_inexistente",
        "mini_sql": f"SELECT * FROM {MINI_TABLE} WHERE id = 999;",
        "pg_sql": f"SELECT * FROM {POSTGRES_TABLE} WHERE id = 999;",
    },
    {
        "name": "rango_id_1_5",
        "mini_sql": f"SELECT * FROM {MINI_TABLE} WHERE id BETWEEN 1 AND 5;",
        "pg_sql": f"SELECT * FROM {POSTGRES_TABLE} WHERE id BETWEEN 1 AND 5;",
    },
]

def post_minisgbd_query(sql: str) -> dict:
    url = f"{MINISGBD_URL}/api/v1/query"
    payload = json.dumps({"sql": sql}).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        raise RuntimeError(f"Mini-SGBD HTTP {e.code}: {body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(
            "No se pudo conectar al Mini-SGBD. "
            "Asegúrate de tener Docker levantado en http://localhost:8000"
        ) from e


def setup_postgres():
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"No existe el CSV: {CSV_PATH}")

    conn = psycopg2.connect(**POSTGRES_CONFIG)
    conn.autocommit = False

    with conn.cursor() as cur:
        cur.execute(f"DROP TABLE IF EXISTS {POSTGRES_TABLE};")
        cur.execute(
            f"""
            CREATE TABLE {POSTGRES_TABLE} (
                id INT PRIMARY KEY,
                nombre VARCHAR(100),
                lat DOUBLE PRECISION,
                lon DOUBLE PRECISION
            );
            """
        )

        with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            rows = [
                (
                    int(row["id"]),
                    row["nombre"],
                    float(row["lat"]),
                    float(row["lon"]),
                )
                for row in reader
            ]

        cur.executemany(
            f"""
            INSERT INTO {POSTGRES_TABLE} (id, nombre, lat, lon)
            VALUES (%s, %s, %s, %s);
            """,
            rows,
        )

        cur.execute(f"CREATE INDEX idx_{POSTGRES_TABLE}_id ON {POSTGRES_TABLE}(id);")

    conn.commit()
    conn.close()

    print(f"PostgreSQL listo: {POSTGRES_TABLE} cargada con {len(rows)} filas.")


def benchmark_minisgbd(case: dict) -> list[dict]:
    results = []

    for i in range(REPEATS):
        start = time.perf_counter()
        response = post_minisgbd_query(case["mini_sql"])
        elapsed_ms = (time.perf_counter() - start) * 1000

        results.append(
            {
                "case": case["name"],
                "engine": "mini_sgbd",
                "repeat": i + 1,
                "client_time_ms": round(elapsed_ms, 4),
                "reported_time_ms": response.get("time_ms"),
                "row_count": response.get("row_count", len(response.get("rows", []))),
            }
        )

    return results


def benchmark_postgres(case: dict) -> list[dict]:
    results = []
    conn = psycopg2.connect(**POSTGRES_CONFIG)

    with conn.cursor() as cur:
        for i in range(REPEATS):
            start = time.perf_counter()
            cur.execute(case["pg_sql"])
            rows = cur.fetchall()
            elapsed_ms = (time.perf_counter() - start) * 1000

            results.append(
                {
                    "case": case["name"],
                    "engine": "postgres",
                    "repeat": i + 1,
                    "client_time_ms": round(elapsed_ms, 4),
                    "reported_time_ms": "",
                    "row_count": len(rows),
                }
            )

    conn.close()
    return results


def save_results(rows: list[dict]):
    results_file = RESULTS_DIR / "benchmark_lugares_results.csv"

    with open(results_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "case",
                "engine",
                "repeat",
                "client_time_ms",
                "reported_time_ms",
                "row_count",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"Resultados guardados en: {results_file}")


def print_summary(rows: list[dict]):
    print("\nResumen:")
    print("-" * 70)

    grouped = {}
    for row in rows:
        key = (row["case"], row["engine"])
        grouped.setdefault(key, []).append(float(row["client_time_ms"]))

    for (case_name, engine), times in grouped.items():
        avg = statistics.mean(times)
        med = statistics.median(times)
        mn = min(times)
        mx = max(times)

        print(
            f"{case_name:20s} | {engine:10s} | "
            f"avg={avg:8.4f} ms | median={med:8.4f} ms | "
            f"min={mn:8.4f} ms | max={mx:8.4f} ms"
        )


def main():
    print("Preparando PostgreSQL...")
    setup_postgres()

    print("\nProbando conexión con Mini-SGBD...")
    post_minisgbd_query(f"SELECT * FROM {MINI_TABLE} WHERE id = 1;")
    print("Mini-SGBD responde correctamente.")

    all_results = []

    for case in TEST_CASES:
        print(f"\nEjecutando caso: {case['name']}")

        mini_rows = benchmark_minisgbd(case)
        pg_rows = benchmark_postgres(case)

        all_results.extend(mini_rows)
        all_results.extend(pg_rows)

    save_results(all_results)
    print_summary(all_results)


if __name__ == "__main__":
    main()