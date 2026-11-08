"""
Pruebas funcionales para los cambios en fix-Rtree:
- Sequential Scan sobre columnas sin índice
- BPlusTree unclustered con duplicados
- RTree como índice espacial (spatial_indexes separado)
- IMPORT FILE (SQL standalone)
- Índices secundarios secundados en _load_csv
"""

import os
import sys
import shutil

# Limpieza de artefactos previos
TEST_DIR = "test_tmp"
if os.path.exists(TEST_DIR):
    shutil.rmtree(TEST_DIR)
os.makedirs(TEST_DIR)

# Parchear DATA_DIR para no contaminar datos reales
import back.engine.database as _db_mod
_db_mod.DATA_DIR = TEST_DIR
_db_mod.CATALOG_DIR = os.path.join(TEST_DIR, "catalog")
_db_mod.CATALOG_META_PATH = os.path.join(TEST_DIR, "catalog", "catalog_meta.json")
_db_mod.PG_CLASS_PATH = os.path.join(TEST_DIR, "catalog", "pg_class.json")
_db_mod.PG_ATTRIBUTE_PATH = os.path.join(TEST_DIR, "catalog", "pg_attribute.json")
_db_mod.PG_INDEX_PATH = os.path.join(TEST_DIR, "catalog", "pg_index.json")
_db_mod.PG_CONSTRAINT_PATH = os.path.join(TEST_DIR, "catalog", "pg_constraint.json")

from back.engine.database import Database
from back.engine.executor import Executor
from back.parser.parser import Parser
from back.storage.schema import Schema, Field, FieldType
from back.storage.page_manager import PageManager
from back.storage.disk_stats import DiskStats
from back.indexes.bplus_tree import BPlusTree


PASS = 0
FAIL = 0

def check(label: str, condition: bool):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS  {label}")
    else:
        FAIL += 1
        print(f"  FAIL  {label}")


# ===========================================================================
# 1. BPlusTree unclustered — duplicados permitidos
# ===========================================================================
print("\n=== 1. BPlusTree unclustered con duplicados ===")

sec_schema = Schema([
    Field("nombre", FieldType.VARCHAR, max_length=20),
    Field("id", FieldType.INT),
], primary_key="nombre")

sec_pm = PageManager(os.path.join(TEST_DIR, "sec_bplus.bin"), DiskStats())
sec_tree = BPlusTree(sec_schema, sec_pm, DiskStats(), clustered=False)

try:
    sec_tree.add_ref("Alice", 1)
    sec_tree.add_ref("Bob", 2)
    sec_tree.add_ref("Alice", 3)  # clave duplicada — NO debe lanzar error
    check("add_ref con clave duplicada no lanza excepcion", True)
except Exception as e:
    check(f"add_ref con clave duplicada no lanza excepcion ({e})", False)

all_refs = list(sec_tree.iter_record_refs())
check("iter_record_refs devuelve 3 entradas con duplicado", len(all_refs) == 3)

alice_records = [r["record"] for r in all_refs if r["record"]["nombre"] == "Alice"]
check("ambas entradas Alice estan presentes", len(alice_records) == 2)

# remove_ref por pk
removed = sec_tree.remove_ref(1)
check("remove_ref(1) elimina primera Alice", removed)
remaining = [r["record"] for r in sec_tree.iter_record_refs() if r["record"]["nombre"] == "Alice"]
check("queda una sola entrada Alice tras remove_ref(1)", len(remaining) == 1)

# Puntero primera hoja persistente
check("_first_leaf_id esta seteado", sec_tree._first_leaf_id is not None)
check("archivo .first_leaf existe en disco", os.path.exists(sec_pm.filepath.replace(".bin", ".first_leaf")))


# ===========================================================================
# 2. Database + executor: RTree en spatial_indexes separado de secondary_indexes
# ===========================================================================
print("\n=== 2. R-Tree como indice espacial (spatial_indexes) ===")

db = Database()
parser = Parser(db=db)
executor = Executor(db)

sql = """CREATE TABLE lugares2 (
    id INT PRIMARY KEY USING BPLUS TREE,
    nombre CHAR(30),
    lat REAL,
    lon REAL
);"""
node = parser.parse(sql)
executor.execute(node)

table = db.get_table("lugares2")
check("tabla creada sin indices secundarios", len(table.secondary_indexes) == 0)
check("tabla creada sin indices espaciales", len(table.spatial_indexes) == 0)

node2 = parser.parse("CREATE INDEX idx_sp ON lugares2 (lat, lon) USING RTREE;")
executor.execute(node2)
table = db.get_table("lugares2")
check("RTree va a spatial_indexes, NO a secondary_indexes", "idx_sp" not in table.secondary_indexes)
check("RTree aparece en spatial_indexes", "idx_sp" in table.spatial_indexes)


# ===========================================================================
# 3. Sequential Scan sobre columna sin indice
# ===========================================================================
print("\n=== 3. Sequential Scan sobre columna sin indice ===")

executor.execute(parser.parse("INSERT INTO lugares2 VALUES (1, 'Lima', -12.046374, -77.042793);"))
executor.execute(parser.parse("INSERT INTO lugares2 VALUES (2, 'Cusco', -13.531950, -71.967463);"))
executor.execute(parser.parse("INSERT INTO lugares2 VALUES (3, 'Arequipa', -16.409047, -71.537451);"))

# nombre no tiene indice — debe usar sequential scan
result = executor.execute(parser.parse("SELECT * FROM lugares2 WHERE nombre = 'Lima';"))
rows = result["results"]
check("SELECT por columna sin indice devuelve 1 resultado", len(rows) == 1)
check("resultado correcto es Lima con id=1", rows and rows[0]["id"] == 1)

# range scan sobre columna sin indice
result2 = executor.execute(parser.parse("SELECT * FROM lugares2 WHERE lat BETWEEN -15.0 AND -10.0;"))
check("BETWEEN sobre columna sin indice devuelve Lima y Cusco", len(result2["results"]) == 2)

# comparison scan sobre columna sin indice
# lat: Lima=-12.04, Arequipa=-16.4 (Cusco ya fue eliminado antes)
# lat < -15.0 solo aplica a Arequipa (-16.4)
result3 = executor.execute(parser.parse("SELECT * FROM lugares2 WHERE lat < -15.0;"))
check("< sobre columna sin indice devuelve solo Arequipa", len(result3["results"]) == 1)

# DELETE por columna sin indice
del_result = executor.execute(parser.parse("DELETE FROM lugares2 WHERE nombre = 'Cusco';"))
check("DELETE por columna sin indice elimina registro", del_result["results"][0]["deleted"])
all_rows = executor.execute(parser.parse("SELECT * FROM lugares2;"))["results"]
check("quedan 2 registros tras DELETE por columna sin indice", len(all_rows) == 2)


# ===========================================================================
# 4. IMPORT FILE (SQL standalone)
# ===========================================================================
print("\n=== 4. IMPORT FILE standalone ===")

# Crear CSV temporal
csv_path = os.path.join(TEST_DIR, "ciudades_test.csv")
with open(csv_path, "w", encoding="utf-8") as f:
    f.write("id,nombre,lat,lon\n")
    f.write("10,Trujillo,-8.112282,-79.028732\n")
    f.write("11,Piura,-5.194169,-80.632816\n")

node_import = parser.parse(f"IMPORT FILE '{csv_path}' INTO lugares2;")
result_imp = executor.execute(node_import)
check("IMPORT FILE devuelve cantidad importada", result_imp["results"][0]["imported"] == 2)

all_after = executor.execute(parser.parse("SELECT * FROM lugares2;"))["results"]
check("despues de IMPORT FILE hay 4 registros en total", len(all_after) == 4)

# Verificar que el indice espacial se actualizó
sp_entry = table.spatial_indexes.get("idx_sp")
if sp_entry:
    pts = sp_entry["index"].all_points()
    check("indice espacial tiene 4 puntos tras IMPORT FILE", len(pts) == 4)
else:
    check("indice espacial existe en tabla", False)


# ===========================================================================
# 5. _load_csv propaga a indices secundarios
# ===========================================================================
print("\n=== 5. _load_csv propaga a indices secundarios ===")

db2 = Database()
parser2 = Parser(db=db2)
executor2 = Executor(db2)

executor2.execute(parser2.parse("""
CREATE TABLE productos (
    id INT PRIMARY KEY USING BPLUS TREE,
    nombre CHAR(20),
    precio REAL
);"""))
executor2.execute(parser2.parse("CREATE INDEX idx_precio ON productos (precio) USING BPLUS TREE;"))

csv_prod = os.path.join(TEST_DIR, "productos.csv")
with open(csv_prod, "w") as f:
    f.write("id,nombre,precio\n")
    f.write("1,Manzana,2.5\n")
    f.write("2,Pera,3.0\n")
    f.write("3,Naranja,2.5\n")

imp_result = executor2.execute(parser2.parse(f"IMPORT FILE '{csv_prod}' INTO productos;"))
check("IMPORT FILE en tabla con indice secundario importa 3", imp_result["results"][0]["imported"] == 3)

# El indice secundario de precio debe tener las 3 referencias
prod_table = db2.get_table("productos")
sec = prod_table.secondary_indexes.get("idx_precio")
if sec:
    refs = list(sec["index"].iter_record_refs())
    check("indice secundario precio tiene 3 entradas tras IMPORT FILE", len(refs) == 3)
else:
    check("indice secundario precio existe", False)


# ===========================================================================
# 6. Catálogo: indices espaciales con ind_is_spatial=True al guardar
# ===========================================================================
print("\n=== 6. Catalogo guarda ind_is_spatial=True para RTree ===")

import json, back.engine.database as _db2
pg_index_path = _db2.PG_INDEX_PATH
if os.path.exists(pg_index_path):
    with open(pg_index_path) as f:
        pg_index = json.load(f)
    spatial_entries = [e for e in pg_index if e.get("ind_is_spatial")]
    check("al menos un entry con ind_is_spatial=True en pg_index", len(spatial_entries) > 0)
else:
    check("pg_index.json existe", False)


# ===========================================================================
# Resumen
# ===========================================================================
print(f"\n{'='*50}")
print(f"RESULTADO: {PASS} PASS  |  {FAIL} FAIL")
print(f"{'='*50}")

shutil.rmtree(TEST_DIR, ignore_errors=True)

if FAIL > 0:
    sys.exit(1)
