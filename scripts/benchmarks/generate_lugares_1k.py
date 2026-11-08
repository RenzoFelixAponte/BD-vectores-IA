from pathlib import Path
import csv

ROOT_DIR = Path(__file__).resolve().parents[2]
INPUT_CSV = ROOT_DIR / "lugares.csv"
OUTPUT_DIR = ROOT_DIR / "scripts" / "benchmarks" / "generated"
OUTPUT_CSV = OUTPUT_DIR / "lugares_1k.csv"

OUTPUT_DIR.mkdir(exist_ok=True)

rows = []

with open(INPUT_CSV, newline="", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    base_rows = list(reader)

target_size = 1000

for i in range(1, target_size + 1):
    base = base_rows[(i - 1) % len(base_rows)]

    rows.append({
        "id": i,
        "nombre": f"{base['nombre']} #{i}",
        "lat": base["lat"],
        "lon": base["lon"],
    })

with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=["id", "nombre", "lat", "lon"])
    writer.writeheader()
    writer.writerows(rows)

print(f"CSV generado: {OUTPUT_CSV}")
print(f"Filas generadas: {len(rows)}")