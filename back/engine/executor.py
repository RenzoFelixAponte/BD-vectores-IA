from .database import Database
from ..indexes import NotSupportedError
from ..indexes.extendible_hashing import ExtendibleHashing
from ..indexes.base_index import DuplicateKeyError
from ..parser.ast_nodes import (
    CreateTableNode, CreateIndexNode, InsertNode, SelectAllNode, SelectEqualNode,
    SelectComparisonNode, SelectRangeNode, SelectPointRadiusNode, SelectKNNNode, DeleteNode,
    DropTableNode, DropIndexNode, ImportFileNode, TextSearchNode, MediaSearchNode,
    SelectCountNode,
)


class ExecutionError(Exception):
    pass


class Executor:
    """
    Toma un nodo AST y lo ejecuta contra la base de datos.
    Retorna siempre {"results": [...], "stats": {"reads", "writes", "time_ms"}}.
    """

    def __init__(self, db: Database):
        self.db = db
        self.stats = db.stats

    # ------------------------------------------------------------------
    # API publica
    # ------------------------------------------------------------------

    def execute(self, node) -> dict:
        """
        Input:  node  cualquier nodo AST del parser
        Output: {"results": list[dict], "stats": dict}
        Raises: ExecutionError si la operacion falla
        """
        self.stats.reset()

        dispatch = {
            CreateTableNode:       self._exec_create,
            CreateIndexNode:       self._exec_create_index,
            DropTableNode:         self._exec_drop_table,
            DropIndexNode:         self._exec_drop_index,
            InsertNode:            self._exec_insert,
            ImportFileNode:        self._exec_import_file,
            SelectAllNode:         self._exec_select_all,
            SelectEqualNode:       self._exec_select_equal,
            SelectComparisonNode:  self._exec_select_comparison,
            SelectRangeNode:       self._exec_select_range,
            SelectPointRadiusNode: self._exec_select_point_radius,
            SelectKNNNode:         self._exec_select_knn,
            SelectCountNode:       self._exec_select_count,
            TextSearchNode:        self._exec_text_search,
            MediaSearchNode:       self._exec_media_search,
            DeleteNode:            self._exec_delete,
        }
        handler = dispatch.get(type(node))
        if handler is None:
            raise ExecutionError(f"Tipo de nodo desconocido: {type(node)}")

        try:
            results = handler(node)
        except (KeyError, ValueError, NotSupportedError) as error:
            raise ExecutionError(str(error)) from error

        return {"results": results, "stats": self.stats.snapshot()}

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _exec_create(self, node: CreateTableNode) -> list:
        """
        Construye el Schema desde las columnas del parser y crea la tabla.
        Si from_file esta presente, carga el CSV.
        """
        schema, column_definitions, primary_index_type = Database.schema_from_columns(node.columns)
        self.db.create_table(
            name=node.table_name,
            schema=schema,
            column_definitions=column_definitions,
            primary_index_type=primary_index_type,
            from_file=node.from_file,
        )
        return []

    def _exec_create_index(self, node: CreateIndexNode) -> list:
        if node.index_type in self.db.CONTENT_INDEX_TYPES:
            summary = self.db.add_content_index(
                node.table_name, node.index_name, node.columns, node.index_type
            )
            return [summary]
        self.db.add_secondary_index(node.table_name, node.index_name, node.columns, node.index_type)
        return []

    def _exec_drop_table(self, node: DropTableNode) -> list:
        self.db.drop_table(node.table_name)
        return []

    def _exec_drop_index(self, node: DropIndexNode) -> list:
        self.db.drop_secondary_index(node.table_name, node.index_name)
        return []

    def _exec_import_file(self, node: ImportFileNode) -> list:
        table = self.db.get_table(node.table_name)
        count = self.db._load_csv(table, node.filepath)
        return [{"imported": count}]

    def _exec_insert(self, node: InsertNode) -> list:
        """
        Mapea los valores posicionales a los campos del schema y llama add().
        """
        table = self.db.get_table(node.table_name)
        fields = table.schema.fields

        if len(node.values) != len(fields):
            raise ExecutionError(
                f"INSERT: se esperaban {len(fields)} valores, "
                f"se recibieron {len(node.values)}"
            )

        record = {}
        for field, value in zip(fields, node.values):
            record[field.name] = self._cast_value(value, field)

        table.index.add(record)
        primary_key_value = record[table.schema.primary_key]
        for secondary_entry in table.secondary_indexes.values():
            try:
                column_name = secondary_entry["columns"][0]
                secondary_entry["index"].add_ref(record[column_name], primary_key_value)
            except DuplicateKeyError:
                pass
        for spatial_entry in table.spatial_indexes.values():
            lat_column, lon_column = spatial_entry["columns"]
            spatial_entry["index"].add_ref(
                record[lat_column],
                record[lon_column],
                primary_key_value,
            )
        return []

    def _exec_select_all(self, node: SelectAllNode) -> list:
        table = self.db.get_table(node.table_name)
        index = table.index
        if isinstance(index, ExtendibleHashing):
            return index.scan_all()
        from ..storage.schema import FieldType
        pk = table.schema.get_field(table.schema.primary_key)
        if pk.field_type == FieldType.INT:
            return index.range_search(-2147483648, 2147483647)
        if pk.field_type == FieldType.FLOAT:
            return index.range_search(float("-inf"), float("inf"))
        return index.range_search("", chr(127) * pk.size)

    def _exec_select_equal(self, node: SelectEqualNode) -> list:
        """Busqueda exacta por clave. Usa indice secundario, PK o sequential scan."""
        table = self.db.get_table(node.table_name)
        for secondary_entry in table.secondary_indexes.values():
            if secondary_entry["columns"] == [node.column]:
                field = table.schema.get_field(node.column)
                key = self._cast_value(node.value, field)
                ref_record = secondary_entry["index"].search(key)
                if ref_record is None:
                    return []
                record = self.db.resolve_primary_key(table, ref_record[table.schema.primary_key])
                return [record] if record is not None else []
        if node.column == table.schema.primary_key:
            key = self._cast_key(node.value, table, node.column)
            result = table.index.search(key)
            return [result] if result is not None else []
        # Sequential scan: sin indice en la columna
        field = table.schema.get_field(node.column)
        key = self._cast_value(node.value, field)
        return [r for r in self._scan_all_records(table) if r.get(node.column) == key]

    def _exec_select_comparison(self, node: SelectComparisonNode) -> list:
        """Busqueda por comparacion. Usa indice secundario, index primario o sequential scan."""
        from ..storage.schema import FieldType

        table = self.db.get_table(node.table_name)
        field = table.schema.get_field(node.column)
        key = self._cast_value(node.value, field)

        # Intenta usar un indice secundario o el primario
        target_index = None
        for secondary_entry in table.secondary_indexes.values():
            if secondary_entry["columns"] == [node.column]:
                target_index = secondary_entry["index"]
                break
        if target_index is None and node.column == table.schema.primary_key:
            target_index = table.index

        if target_index is not None:
            if field.field_type == FieldType.INT:
                begin, end = -2147483648, 2147483647
            elif field.field_type == FieldType.FLOAT:
                begin, end = float("-inf"), float("inf")
            elif field.field_type == FieldType.BOOL:
                begin, end = False, True
            else:
                begin, end = "", chr(127) * field.size

            if node.operator in ("<", "<="):
                results = target_index.range_search(begin, key)
            else:
                results = target_index.range_search(key, end)

            if target_index is not table.index:
                results = [
                    self.db.resolve_primary_key(table, ref[table.schema.primary_key])
                    for ref in results if ref is not None
                ]

            ops = {"<": lambda v: v < key, "<=": lambda v: v <= key,
                   ">": lambda v: v > key, ">=": lambda v: v >= key}
            fn = ops.get(node.operator)
            if fn is None:
                raise ExecutionError(f"Operador de comparacion no soportado: '{node.operator}'")
            return [r for r in results if fn(r[node.column])]

        # Sequential scan fallback
        ops = {"<": lambda v: v < key, "<=": lambda v: v <= key,
               ">": lambda v: v > key, ">=": lambda v: v >= key}
        fn = ops.get(node.operator)
        if fn is None:
            raise ExecutionError(f"Operador de comparacion no soportado: '{node.operator}'")
        return [r for r in self._scan_all_records(table) if fn(r.get(node.column))]

    def _exec_select_range(self, node: SelectRangeNode) -> list:
        """Busqueda por rango [begin, end]. Usa indice, PK o sequential scan."""
        table = self.db.get_table(node.table_name)
        for secondary_entry in table.secondary_indexes.values():
            if secondary_entry["columns"] == [node.column]:
                field = table.schema.get_field(node.column)
                begin = self._cast_value(node.begin, field)
                end = self._cast_value(node.end, field)
                refs = secondary_entry["index"].range_search(begin, end)
                return [
                    self.db.resolve_primary_key(table, ref[table.schema.primary_key])
                    for ref in refs if ref is not None
                ]
        if node.column == table.schema.primary_key:
            begin = self._cast_key(node.begin, table, node.column)
            end = self._cast_key(node.end, table, node.column)
            return table.index.range_search(begin, end)
        # Sequential scan fallback
        field = table.schema.get_field(node.column)
        begin = self._cast_value(node.begin, field)
        end = self._cast_value(node.end, field)
        return [r for r in self._scan_all_records(table) if begin <= r.get(node.column) <= end]

    def _exec_select_point_radius(self, node: SelectPointRadiusNode) -> list:
        """Busqueda espacial por radio. Solo valida para indices espaciales."""
        table = self.db.get_table(node.table_name)
        for spatial_entry in table.spatial_indexes.values():
            refs = spatial_entry["index"].range_search(node.point, node.radius)
            return [self.db.resolve_primary_key(table, ref) for ref in refs]
        raise ExecutionError(f"La tabla '{node.table_name}' no tiene un indice espacial")

    def _exec_select_knn(self, node: SelectKNNNode) -> list:
        """Busqueda de k vecinos mas cercanos. Solo valida para indices espaciales."""
        table = self.db.get_table(node.table_name)
        for spatial_entry in table.spatial_indexes.values():
            refs = spatial_entry["index"].knn(node.point, node.k)
            return [self.db.resolve_primary_key(table, ref) for ref in refs]
        raise ExecutionError(f"La tabla '{node.table_name}' no tiene un indice espacial")

    def _exec_select_count(self, node: SelectCountNode) -> list:
        """SELECT COUNT(*) FROM tabla [WHERE col = valor]. Devuelve [{'count': n}]."""
        table = self.db.get_table(node.table_name)
        records = self._scan_all_records(table)
        if node.column is not None:
            field = table.schema.get_field(node.column)
            key = self._cast_value(node.value, field)
            count = sum(1 for r in records if r.get(node.column) == key)
        else:
            count = len(records)
        return [{"count": count}]

    # ------------------------------------------------------------------
    # Recuperacion por contenido (Proyecto 2) -- puntos de integracion
    # ------------------------------------------------------------------

    def _exec_text_search(self, node: TextSearchNode) -> list:
        """Recuperacion de texto por similitud de coseno (operador @@)."""
        table = self.db.get_table(node.table_name)
        entry = self._find_content_index(table, node.column, "inverted")
        if entry is None:
            raise ExecutionError(
                f"La columna '{node.column}' no tiene un indice INVERTED; "
                f"crealo con CREATE INDEX ... ON {node.table_name} ({node.column}) USING INVERTED"
            )
        documents = None
        if node.method == "sequential":
            from ..retrieval.text.tokenizer import Tokenizer
            tok = entry["retriever"].tokenizer
            documents = [
                (rec["record"][table.schema.primary_key],
                 tok.process(rec["record"].get(node.column) or ""))
                for rec in table.index.iter_record_refs()
            ]
        hits = entry["retriever"].search(node.query_text, node.k, method=node.method, documents=documents)
        return self._resolve_hits(table, hits)

    def _exec_media_search(self, node: MediaSearchNode) -> list:
        """Recuperacion multimedia por KNN sobre histogramas Bag of Words (operador <->)."""
        table = self.db.get_table(node.table_name)
        entry = self._find_content_index(table, node.column, "multimedia")
        if entry is None:
            raise ExecutionError(
                f"La columna '{node.column}' no tiene un indice MULTIMEDIA; "
                f"crealo con CREATE INDEX ... ON {node.table_name} ({node.column}) USING MULTIMEDIA"
            )
        hits = entry["retriever"].search(node.query_path, node.k, method=node.method)
        return self._resolve_hits(table, hits)

    def _find_content_index(self, table, column: str, index_type: str):
        for entry in table.content_indexes.values():
            if entry["type"] == index_type and entry["columns"] == [column]:
                return entry
        return None

    def _resolve_hits(self, table, hits: list) -> list:
        """Convierte [(doc_id, score)] en filas completas, agregando _score y _rank."""
        results = []
        for rank, (doc_id, score) in enumerate(hits, start=1):
            record = self.db.resolve_primary_key(table, doc_id)
            if record is None:
                continue
            row = dict(record)
            row["_score"] = round(float(score), 6)
            row["_rank"] = rank
            results.append(row)
        return results

    def _exec_delete(self, node: DeleteNode) -> list:
        """Elimina el registro con la clave dada. Soporta PK, indice secundario y sequential scan."""
        table = self.db.get_table(node.table_name)
        record = None
        primary_key_value = None

        if node.column == table.schema.primary_key:
            key = self._cast_key(node.value, table, node.column)
            record = table.index.search(key)
            primary_key_value = key
        else:
            for secondary_entry in table.secondary_indexes.values():
                if secondary_entry["columns"] == [node.column]:
                    field = table.schema.get_field(node.column)
                    sec_key = self._cast_value(node.value, field)
                    ref_record = secondary_entry["index"].search(sec_key)
                    if ref_record is not None:
                        record = self.db.resolve_primary_key(
                            table, ref_record[table.schema.primary_key],
                        )
                        if record is not None:
                            primary_key_value = record[table.schema.primary_key]
                    break
            else:
                # Sequential scan: no hay indice en la columna
                field = table.schema.get_field(node.column)
                sec_key = self._cast_value(node.value, field)
                for r in self._scan_all_records(table):
                    if r.get(node.column) == sec_key:
                        record = r
                        primary_key_value = r[table.schema.primary_key]
                        break

        if record is None or primary_key_value is None:
            return [{"deleted": False}]

        for secondary_entry in table.secondary_indexes.values():
            secondary_entry["index"].remove_ref(primary_key_value)
        for spatial_entry in table.spatial_indexes.values():
            spatial_entry["index"].remove_ref(primary_key_value)

        removed = table.index.remove(primary_key_value)
        return [{"deleted": removed}]

    # ------------------------------------------------------------------
    # Sequential Scan
    # ------------------------------------------------------------------

    def _scan_all_records(self, table) -> list[dict]:
        """Recorre todos los registros del indice primario sin filtro."""
        if isinstance(table.index, ExtendibleHashing):
            return table.index.scan_all()
        return [item["record"] for item in table.index.iter_record_refs()]

    # ------------------------------------------------------------------
    # Utilidades de casting
    # ------------------------------------------------------------------

    def _cast_key(self, raw_value, table, column_name):
        """Convierte el valor literal del parser al tipo Python del campo."""
        try:
            field = table.schema.get_field(column_name)
        except KeyError:
            raise ExecutionError(
                f"Columna '{column_name}' no existe en '{table.name}'"
            )
        return self._cast_value(raw_value, field)

    def _cast_value(self, value, field):
        """Convierte value al tipo correcto del Field."""
        from ..storage.schema import FieldType

        if field.field_type == FieldType.INT:
            return int(value)
        if field.field_type == FieldType.FLOAT:
            return float(value)
        if field.field_type == FieldType.BOOL:
            if isinstance(value, bool):
                return value
            return str(value).lower() in ("true", "1", "yes")
        return str(value)
