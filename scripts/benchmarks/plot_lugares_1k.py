from pathlib import Path
import csv
from collections import defaultdict
import statistics
import matplotlib.pyplot as plt
import numpy as np

BASE_DIR = Path(__file__).resolve().parent
RESULTS_CSV = BASE_DIR / "results" / "benchmark_lugares_1k_results.csv"
OUTPUT_DIR = BASE_DIR / "results"
OUTPUT_IMG = OUTPUT_DIR / "benchmark_lugares_1k_avg.png"

data = defaultdict(list)

with open(RESULTS_CSV, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        key = (row["case"], row["engine"])
        data[key].append(float(row["client_time_ms"]))

cases = sorted(set(case for case, engine in data.keys()))

mini_values = [
    statistics.mean(data[(case, "mini_sgbd")])
    for case in cases
]

postgres_values = [
    statistics.mean(data[(case, "postgres")])
    for case in cases
]

x = np.arange(len(cases))
width = 0.35

plt.figure(figsize=(10, 6))

plt.bar(x - width / 2, mini_values, width, label="Mini-SGBD", color="#2563eb")
plt.bar(x + width / 2, postgres_values, width, label="PostgreSQL", color="#f97316")

plt.ylabel("Tiempo promedio (ms)")
plt.title("Benchmark Nivel 1 - 1K registros: Mini-SGBD vs PostgreSQL")
plt.xticks(x, cases, rotation=20, ha="right")
plt.legend()
plt.tight_layout()

plt.savefig(OUTPUT_IMG, dpi=200)

print(f"Gráfico guardado en: {OUTPUT_IMG}")