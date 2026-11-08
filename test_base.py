from back.storage.schema import Schema, Field, FieldType
from back.storage.page_manager import PageManager
from back.storage.disk_stats import DiskStats
from back.indexes.bplus_tree import BPlusTree
import os

if os.path.exists("growth_test.bin"):
    os.remove("growth_test.bin")

stats = DiskStats()
pm = PageManager("growth_test.bin", stats)
schema = Schema([
    Field("id", FieldType.INT),
    Field("nombre", FieldType.VARCHAR, max_length=10)
], primary_key="id")

tree = BPlusTree(schema, pm, stats)
datos = [
    {"id": 10, "nombre": "Liss"},
    {"id": 20, "nombre": "Ximena"},
    {"id": 30, "nombre": "UTEC"},
    {"id": 40, "nombre": "Python"},
    {"id": 50, "nombre": "Data"}
]

print("--- Insertando datos ---")
for d in datos:
    tree.add(d)
    print(f"✅ ID {d['id']} insertado correctamente")

print("\n--- Probando Búsqueda por Rango (15 a 45) ---")
resultados = tree.range_search(15, 45)
if len(resultados) == 3:
    print("✅ ¡EXITO! Rango funciona.")
else:
    print(f"❌ Error en rango: se obtuvieron {len(resultados)}")

# --- PRUEBA DEL JEFE FINAL: REMOVE ---
print("\n--- Probando Eliminación (ID 20) ---")

# Verificamos que existe antes de borrar
antes = tree.search(20)
print(f"Buscando 20 antes de borrar: {'Encontrado (' + antes['nombre'] + ')' if antes else 'No existe'}")

# Ejecutamos el remove
exito = tree.remove(20)

# Verificamos que ya no existe
despues = tree.search(20)
if exito and despues is None:
    print("🚀 ¡PERFECTO! El ID 20 fue eliminado y el árbol sigue íntegro.")
else:
    print("❌ Falló la eliminación o el registro sigue ahí.")