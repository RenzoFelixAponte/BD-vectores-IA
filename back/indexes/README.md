# Implementación de Índices

Cada índice hereda de `Index` (base_index.py) e implementa los mismos 4 métodos.
El motor llama siempre igual sin importar cuál índice es — **no cambien las firmas**.

---

## Archivos y responsables sugeridos

| Archivo | Índice |
|---|---|
| `sequential_file.py` | Sequential File |
| `extendible_hashing.py` | Extendible Hashing |
| `bplus_tree.py` | B+ Tree |
| `rtree.py` | R-Tree espacial |

---

## Reglas que TODOS deben respetar

1. **Nunca cargar el archivo completo en memoria.** Usar siempre `self.pm.read_page(page_id)` y `self.pm.write_page(page_id, data)`.
2. **Serializar con el schema.** Para convertir un dict a bytes: `self.schema.serialize(record)`. Para leer de disco: `self.schema.deserialize(data)`.
3. **No usar librerías externas** para la lógica del índice.
4. Todos los métodos deben funcionar con **cualquier tipo de clave** (int, float, str) — el schema ya lo maneja.

---

## Cómo usar PageManager

```python
# Leer una página (4KB)
raw = self.pm.read_page(page_id)          # bytes de 4096B

# Escribir una página
self.pm.write_page(page_id, data)         # data <= 4096 bytes

# Crear nueva página al final del archivo
new_id = self.pm.allocate_page()          # retorna el page_id

# Cuántos registros caben por página
cap = self.pm.records_per_page(self.schema.record_size)
```

---

## Cómo serializar registros

```python
# dict → bytes (para guardar en disco)
raw = self.schema.serialize({"id": 1, "nombre": "Ana", "saldo": 100.0})

# bytes → dict (para leer de disco)
record = self.schema.deserialize(raw)

# Tamaño fijo de cada registro en bytes
size = self.schema.record_size

# Leer el campo de la clave primaria de un registro
pk_field = self.schema.primary_key          # nombre del campo ("id")
key = record[pk_field]
```

---

## Sequential File (`sequential_file.py`)

**Idea:** archivo principal ordenado + archivo auxiliar de desbordamiento.

- `add` → escribe en el auxiliar. Si auxiliar tiene `K` registros → llamar `_rebuild()`.
- `search` → búsqueda binaria en principal (por página) + scan lineal en auxiliar.
- `range_search` → binaria para `begin`, luego scan secuencial hasta `end`.
- `remove` → marcar registro con un flag de eliminado (1 byte extra en la página). Se limpia en `_rebuild`.
- `_rebuild` → merge principal + auxiliar → nuevo archivo principal ordenado. Vaciar auxiliar.

**Layout de página:**
```
[2B count][record_0][record_1]...[record_N]
```
Cada registro puede tener un byte de flag: `0x00` = activo, `0xFF` = eliminado.

---

## Extendible Hashing (`extendible_hashing.py`)

**Idea:** directorio de buckets que crece dinámicamente.

- `add` → `hash(key) & mask` → bucket → insertar. Si bucket lleno → `_split_bucket`.
- `search` → `hash(key) & mask` → leer página del bucket → scan lineal.
- `range_search` → **lanzar `NotSupportedError`** (hashing no soporta rangos).
- `remove` → `hash(key) & mask` → bucket → marcar eliminado.
- `_hash(key, depth)` → retorna los `depth` bits bajos del hash de `key`.
- `_split_bucket` → duplica profundidad local, redistribuye registros.

**Archivos:**
- `nombre.bin` → páginas de buckets (datos).
- `nombre_dir.bin` → directorio: `[global_depth(4B)][page_id_0(4B)][page_id_1(4B)]...`

---

## B+ Tree (`bplus_tree.py`)

**Idea:** árbol balanceado con hojas enlazadas para range_search eficiente.

- `add` → bajar hasta la hoja correcta → insertar ordenado → si overflow → `_split_leaf` → propagar hacia arriba.
- `search` → desde raíz, en cada nodo interno elegir hijo → llegar a hoja → scan.
- `range_search` → `_find_leaf(begin)` → scan de hojas enlazadas (`next_leaf`) hasta pasar `end`.
- `remove` → borrar de hoja → si underflow → merge o redistribuir con hermano.

**Layout de nodo (una página):**
```
[type(1B)][key_count(2B)][keys...][children_page_ids o records...]
[next_leaf(4B)]   ← solo en nodos hoja
```
- `type = 0` → nodo interno, `type = 1` → hoja.

---

## R-Tree (`rtree.py`)

**Idea:** árbol de MBRs (Minimum Bounding Rectangles) para datos espaciales.

- `add` → `_choose_leaf` (menor expansión de MBR) → insertar → `_adjust_tree` (actualizar MBRs).
- `range_search(point, radius)` → podar nodos cuyo MBR no intersecta el círculo (`_mbr_intersects_circle`) → colectar hojas dentro del radio usando `_haversine`.
- `knn(point, k)` → priority queue ordenada por distancia al MBR → expandir nodos más cercanos primero.
- `remove(key)` → buscar hoja con ese punto → eliminar entrada → ajustar MBRs.
- `_haversine(p1, p2)` → distancia en km entre dos puntos (lat, lon).

**Layout de entrada en nodo:**
```
# Nodo interno:  [min_lat(8B)][min_lon(8B)][max_lat(8B)][max_lon(8B)][child_page_id(4B)]
# Nodo hoja:     [min_lat(8B)][min_lon(8B)][max_lat(8B)][max_lon(8B)][record(schema.record_size B)]
```

---

## Cómo probar tu índice

Crear un archivo `test_<tu_indice>.py` en la raíz del `back/`:

```python
import tempfile, os
from storage import Schema, Field, FieldType, PageManager, DiskStats
from indexes.sequential_file import SequentialFile  # cambiar según tu índice

schema = Schema([
    Field("id",     FieldType.INT),
    Field("nombre", FieldType.VARCHAR, max_length=30),
], primary_key="id")

stats = DiskStats()
with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as f:
    path = f.name

pm = PageManager(path, stats)
# Para sequential también necesitas aux_pm — ver constructor del archivo

# índice = SequentialFile(schema, pm, aux_pm, stats)

# índice.add({"id": 1, "nombre": "Ana"})
# print(índice.search(1))
# print(índice.range_search(1, 10))
# print(índice.remove(1))

os.unlink(path)
```
