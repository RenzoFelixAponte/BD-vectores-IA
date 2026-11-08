import time
import random
import os
from back.storage.schema import Schema, Field, FieldType
from back.storage.page_manager import PageManager
from back.storage.disk_stats import DiskStats
from back.indexes.bplus_tree import BPlusTree

# 1. Setup Limpio
if os.path.exists("stress_test.bin"): os.remove("stress_test.bin")

stats = DiskStats()
pm = PageManager("stress_test.bin", stats)
schema = Schema([
    Field("id", FieldType.INT),
    Field("valor", FieldType.FLOAT)
], primary_key="id")
tree = BPlusTree(schema, pm, stats)

# 2. Generar 10,000 datos aleatorios
n = 10000
ids = list(range(n))
random.shuffle(ids) # Los insertamos desordenados para estresar al árbol

print(f"--- Iniciando Carga Masiva de {n} registros ---")
start_time = time.time()

for i in ids:
    tree.add({"id": i, "valor": random.uniform(0, 100)})

end_time = time.time()

# 3. Resultados
print(f"✅ ¡Carga completada en {end_time - start_time:.2f} segundos!")
print(f"📊 Lecturas a disco: {stats.reads}")
print(f"📊 Escrituras a disco: {stats.writes}")

# 4. Verificación de integridad
print("\n--- Verificando 5 búsquedas al azar ---")
muestras = random.sample(ids, 5)
for m in muestras:
    res = tree.search(m)
    print(f" -> Buscando ID {m}... {'Encontrado' if res else '❌ PERDIDO'}")