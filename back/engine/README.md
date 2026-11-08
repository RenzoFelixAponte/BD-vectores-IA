# Engine

Este modulo implementa el motor de ejecucion actual del proyecto. Su trabajo es recibir nodos AST ya validados por el parser, resolver la tabla e indices involucrados, ejecutar la operacion fisica correspondiente y devolver resultados junto con metricas de I/O.

En el estado actual del proyecto, el `engine` esta compuesto por tres piezas principales:

- `database.py`
- `executor.py`
- `table.py`

## Responsabilidades Generales

El `engine` actual se encarga de:

- Mantener en memoria el conjunto de tablas disponibles
- Reconstruir tablas e indices desde el catalogo persistido
- Crear y eliminar tablas
- Crear y eliminar indices secundarios
- Ejecutar inserciones, consultas y eliminaciones
- Coordinar la actualizacion del indice primario y de los indices secundarios
- Producir metricas de lecturas, escrituras y tiempo

La entrada natural del modulo es un nodo AST producido por `Parser.parse(sql)`. La salida natural es un diccionario con esta forma:

```python
{
    "results": [...],
    "stats": {
        "reads": ...,
        "writes": ...,
        "time_ms": ...
    }
}
```

## Estructura Del Modulo

### `database.py`

`Database` es el punto de entrada principal del motor. Administra el conjunto de tablas cargadas y coordina catalogo, almacenamiento e indices.

Responsabilidades actuales:

- Cargar el catalogo del sistema al iniciar
- Reconstruir objetos `Table` desde `pg_class`, `pg_attribute`, `pg_index` y `pg_constraint`
- Crear tablas nuevas a partir del esquema derivado desde el parser
- Construir el indice primario de cada tabla
- Agregar indices secundarios escalares o `RTree`
- Eliminar tablas e indices secundarios
- Persistir de nuevo el catalogo cuando cambia la estructura de la base
- Cargar datos desde CSV durante `CREATE TABLE ... FROM FILE`
- Resolver una llave primaria hacia su registro completo

Archivos de catalogo usados actualmente:

- `back/data/catalog/catalog_meta.json`
- `back/data/catalog/pg_class.json`
- `back/data/catalog/pg_attribute.json`
- `back/data/catalog/pg_index.json`
- `back/data/catalog/pg_constraint.json`

El `Database` tambien decide que implementacion fisica de indice se debe instanciar segun el tipo solicitado:

- `SequentialFile`
- `ExtendibleHashing`
- `BPlusTree`
- `RTree`

Los tipos de indice reconocidos por el motor son:

- `sequential`
- `hashing`
- `bplus`
- `rtree`

Para llave primaria solo se aceptan:

- `sequential`
- `hashing`
- `bplus`

### `table.py`

`Table` representa una tabla cargada en memoria. Es un contenedor liviano de metadatos y referencias a las estructuras fisicas.

Cada objeto `Table` mantiene:

- `name`: nombre de la tabla
- `schema`: objeto `Schema` de la capa de almacenamiento
- `index`: indice primario que almacena y recupera los registros
- `column_definitions`: definicion declarada de columnas usada por catalogo y semantica
- `primary_index_type`: tecnica del indice primario
- `rel_oid`: OID de la tabla en `pg_class`
- `primary_index_oid`: OID del indice primario en `pg_class`
- `primary_index_name`: nombre catalogado del indice primario
- `primary_constraint_name`: nombre catalogado de la restriccion `PRIMARY KEY`
- `secondary_indexes`: diccionario de indices secundarios

Cada entrada de `secondary_indexes` tiene esta estructura logica:

```python
{
    "index": ...,
    "type": "bplus" | "hashing" | "sequential" | "rtree",
    "columns": [...],
    "rel_oid": ...,
    "storage_name": ...
}
```

### `executor.py`

`Executor` recibe un nodo AST y ejecuta la operacion correspondiente sobre una instancia de `Database`.

Su metodo principal es:

```python
execute(node) -> {"results": ..., "stats": ...}
```

Antes de ejecutar cualquier consulta, el `Executor` reinicia las metricas de disco con `self.stats.reset()`.

Despues usa un `dispatch` por tipo de nodo AST para dirigir la operacion al handler adecuado.

Nodos soportados actualmente:

- `CreateTableNode`
- `CreateIndexNode`
- `DropTableNode`
- `DropIndexNode`
- `InsertNode`
- `SelectAllNode`
- `SelectEqualNode`
- `SelectComparisonNode`
- `SelectRangeNode`
- `SelectPointRadiusNode`
- `SelectKNNNode`
- `DeleteNode`

## Flujo General De Ejecucion

El flujo actual del `engine` es:

1. El parser devuelve un nodo AST ya validado lexica, sintactica y semanticamente
2. `Executor.execute(node)` reinicia metricas
3. El `Executor` selecciona el handler correspondiente
4. El handler consulta `Database` para abrir la tabla
5. El handler llama al indice primario o secundario segun el tipo de operacion
6. El `Executor` devuelve resultados y snapshot de metricas

## Operaciones Soportadas

### `CREATE TABLE`

El handler `_exec_create()`:

- toma las columnas declaradas en el AST
- llama `Database.schema_from_columns(...)`
- obtiene `Schema`, `column_definitions` y `primary_index_type`
- crea la tabla con `Database.create_table(...)`
- si existe `FROM FILE`, carga el CSV en la estructura primaria

La tabla se registra en memoria y luego en los catalogos del sistema.

### `CREATE INDEX`

El handler `_exec_create_index()` delega completamente en:

```python
Database.add_secondary_index(table_name, index_name, columns, index_type)
```

Durante esa operacion:

- se valida la tabla objetivo
- se construye el esquema fisico del indice secundario
- se instancia la estructura fisica correspondiente
- se puebla el indice con los registros ya existentes
- se persiste el nuevo estado en catalogo

Para indices escalares, el secundario guarda referencias por llave primaria. Para `RTree`, el indice guarda referencias espaciales hacia la llave primaria.

### `DROP TABLE`

`_exec_drop_table()` llama:

```python
Database.drop_table(table_name)
```

Esa operacion:

- elimina archivos fisicos asociados a la tabla
- elimina la tabla del conjunto en memoria
- actualiza el catalogo del sistema

### `DROP INDEX`

`_exec_drop_index()` llama:

```python
Database.drop_secondary_index(table_name, index_name)
```

Esa operacion:

- elimina la entrada del indice secundario en memoria
- elimina sus archivos fisicos
- actualiza el catalogo del sistema

### `INSERT`

`_exec_insert()` realiza insercion posicional de valores.

Flujo actual:

1. abre la tabla
2. compara el numero de valores con el numero de campos del `schema`
3. convierte cada valor al tipo Python esperado por el `Field`
4. inserta el registro completo en el indice primario
5. obtiene la llave primaria del registro
6. actualiza cada indice secundario con una referencia a esa llave primaria

Para secundarios escalares:

- se llama `add_ref(clave_secundaria, primary_key_value)`

Para `RTree`:

- se llama `add_ref(lat, lon, primary_key_value)`

Si un secundario encuentra una clave duplicada durante la propagacion, el `Executor` captura `DuplicateKeyError` y continua.

### `SELECT *`

`_exec_select_all()` devuelve todos los registros de la tabla.

El comportamiento depende del indice primario:

- si el primario es `RTree`, usa `all_points()`
- si el primario es `ExtendibleHashing`, usa `scan_all()`
- en otros casos usa `range_search(...)` sobre el rango total del tipo de la PK

### `SELECT ... WHERE columna = valor`

`_exec_select_equal()` hace busqueda exacta.

Flujo actual:

- si existe un indice secundario escalar sobre esa columna, busca primero en el secundario
- el secundario devuelve la referencia con la PK
- `Database.resolve_primary_key(...)` recupera el registro real desde el indice primario
- si no existe secundario aplicable, se busca directamente en el indice primario

### `SELECT ... WHERE columna <, <=, >, >= valor`

`_exec_select_comparison()` resuelve consultas por comparacion simple.

Flujo actual:

- determina el tipo del campo
- calcula el rango minimo y maximo del tipo
- intenta usar un secundario escalar si existe sobre la columna
- si usa secundario, resuelve cada referencia hacia el registro primario
- aplica un filtro final en memoria para respetar estrictamente el operador solicitado

### `SELECT ... WHERE columna BETWEEN a AND b`

`_exec_select_range()` realiza busquedas por rango inclusivo.

Flujo actual:

- si existe secundario escalar sobre la columna, usa ese indice
- resuelve cada referencia a traves de la PK
- si no existe secundario, usa `range_search(begin, end)` sobre el indice primario

### Consultas Espaciales

Se soportan dos variantes:

- `IN (POINT(x, y), RADIUS r)`
- `IN (POINT(x, y), K k)`

`_exec_select_point_radius()`:

- localiza un indice secundario `RTree`
- ejecuta `range_search(node.point, node.radius)`
- resuelve cada PK hacia su registro completo

`_exec_select_knn()`:

- localiza un indice secundario `RTree`
- ejecuta `knn(node.point, node.k)`
- resuelve cada PK hacia su registro completo

Si la tabla no tiene `RTree`, el `Executor` lanza `ExecutionError`.

### `DELETE`

`_exec_delete()` soporta eliminacion por igualdad.

Flujo actual:

- si la columna filtrada es la llave primaria, busca el registro directamente en el primario
- si la columna filtrada tiene indice secundario escalar, busca la referencia secundaria y luego resuelve el registro real
- si no encuentra el registro, devuelve `{"deleted": False}`
- si lo encuentra, elimina primero las referencias en indices secundarios mediante `remove_ref(primary_key_value)`
- luego elimina el registro del indice primario con `remove(primary_key_value)`
- devuelve `{"deleted": removed}`

## Conversion De Tipos

El `Executor` convierte los literales del parser a tipos Python con `_cast_value(...)`.

Reglas actuales:

- `FieldType.INT` -> `int`
- `FieldType.FLOAT` -> `float`
- `FieldType.BOOL` -> `bool`
- `FieldType.VARCHAR` -> `str`

`DATE`, `TIME` y `CHAR(n)` se almacenan actualmente como `VARCHAR` dentro del `Schema` de almacenamiento, aunque su tipo declarado original se conserva en `column_definitions` y en `pg_attribute`.

## Catalogo Y Reconstruccion

Al iniciar, `Database` reconstruye el estado del motor desde los catalogos.

Proceso actual:

1. leer `catalog_meta.json`
2. leer `pg_class.json`
3. leer `pg_attribute.json`
4. leer `pg_index.json`
5. leer `pg_constraint.json`
6. identificar las filas `rel_kind == "table"`
7. reconstruir columnas, PK e indices primarios y secundarios
8. reabrir sus archivos fisicos desde `back/data`
9. registrar cada tabla en `self._tables`

Cuando cambia la estructura de la base, `_save_catalogs()` vuelve a materializar esos cuatro catalogos mas `catalog_meta.json`.

## Almacenamiento Fisico

El `engine` no implementa por si solo paginas o serializacion binaria. Esa responsabilidad pertenece a la capa `storage` y a los metodos de acceso en `indexes`.

Sin embargo, el `engine` define la convencion de nombres de archivos:

- indice principal o secundario base: `back/data/<table_name>_<storage_name>.bin`
- auxiliar de `SequentialFile`: `..._aux.bin`
- directorio de `ExtendibleHashing`: `..._dir.bin`
- raiz persistida de otras estructuras cuando aplique: `... .root`

Ejemplos:

- `employee_pk_id.bin`
- `employee_pk_id_aux.bin`
- `pokemon_pk_pokedex_number.bin`
- `pokemon_pk_pokedex_number_dir.bin`
- `cities_idx_cities_coords.bin`

## Metricas

Las metricas se apoyan en `DiskStats` desde la capa `storage`.

El ciclo actual es:

- `Executor.execute()` reinicia las metricas
- los indices y `PageManager` acumulan lecturas y escrituras
- el `Executor` devuelve `self.stats.snapshot()` al final

Las metricas expuestas al resto del sistema son:

- lecturas
- escrituras
- tiempo total en milisegundos

## Manejo De Errores

`Executor` expone errores de ejecucion mediante `ExecutionError`.

Actualmente captura y traduce:

- `KeyError`
- `ValueError`
- `NotSupportedError`

Errores de parsing y semantica no nacen en este modulo, porque deben haber sido resueltos antes de que el nodo llegue al `engine`.

## Resumen Operativo

En su version actual, el `engine` del proyecto funciona como una capa que:

- recibe AST ya validado
- administra tablas cargadas en memoria
- mantiene catalogo persistido del sistema
- usa el indice primario como estructura principal de almacenamiento y recuperacion
- usa indices secundarios como aceleradores por referencia a PK
- ejecuta consultas escalares, de rango y espaciales
- devuelve resultados junto con metricas de I/O

Ese es el comportamiento definitivo del modulo en el estado actual del proyecto.
