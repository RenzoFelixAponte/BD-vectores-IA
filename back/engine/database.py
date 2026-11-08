import csv
import json
import os
import shutil

from .table import Table
from ..indexes import BPlusTree, ExtendibleHashing, RTree, SequentialFile
from ..storage import DiskStats, Field, FieldType, PageManager, Schema

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
CATALOG_DIR = os.path.join(DATA_DIR, "catalog")
CATALOG_META_PATH = os.path.join(CATALOG_DIR, "catalog_meta.json")
PG_CLASS_PATH = os.path.join(CATALOG_DIR, "pg_class.json")
PG_ATTRIBUTE_PATH = os.path.join(CATALOG_DIR, "pg_attribute.json")
PG_INDEX_PATH = os.path.join(CATALOG_DIR, "pg_index.json")
PG_CONSTRAINT_PATH = os.path.join(CATALOG_DIR, "pg_constraint.json")
DEFAULT_NEXT_OID = 1000


class Database:
    """
    Gestiona el conjunto de tablas en memoria y en disco.
    Punto de entrada principal del motor.
    """

    INDEX_TYPES = {"sequential", "hashing", "bplus", "rtree"}
    PRIMARY_INDEX_TYPES = {"sequential", "hashing", "bplus"}
    SPATIAL_INDEX_TYPES = {"rtree"}

    def __init__(self):
        self._tables: dict[str, Table] = {}
        self.stats = DiskStats()
        self._catalog_meta = {"next_oid": DEFAULT_NEXT_OID}
        self._ensure_data_dir()
        self._load_catalogs()

    # ------------------------------------------------------------------
    # API publica
    # ------------------------------------------------------------------

    def create_table(
        self,
        name: str,
        schema: Schema,
        column_definitions: list,
        primary_index_type: str = "bplus",
        from_file: str = None,
    ) -> Table:
        if name in self._tables:
            raise ValueError(f"La tabla '{name}' ya existe")
        if primary_index_type not in self.PRIMARY_INDEX_TYPES:
            raise ValueError(
                "La llave primaria solo puede usar SEQUENTIAL, EXTENDIBLE HASHING o BPLUS TREE"
            )

        self._ensure_data_dir()
        pk_storage_name = self._primary_storage_name(schema.primary_key)
        index = self._build_index(name, pk_storage_name, schema, primary_index_type, [schema.primary_key])
        table = Table(
            name,
            schema,
            index,
            column_definitions,
            primary_index_type,
            rel_oid=self._allocate_oid(),
            primary_index_oid=self._allocate_oid(),
            primary_index_name=self._primary_index_rel_name(name, schema.primary_key),
            primary_constraint_name=self._primary_constraint_name(name),
        )
        self._tables[name] = table

        if from_file:
            self._load_csv(table, from_file)

        self._save_catalogs()
        return table

    def get_table(self, name: str) -> Table:
        if name not in self._tables:
            raise KeyError(f"Tabla '{name}' no existe")
        return self._tables[name]

    def add_secondary_index(self, table_name: str, index_name: str, columns: list, index_type: str) -> None:
        table = self.get_table(table_name)
        all_index_names = set(table.secondary_indexes) | set(table.spatial_indexes)
        if index_name in all_index_names:
            raise ValueError(f"Ya existe un indice llamado '{index_name}' en '{table_name}'")
        if index_type not in self.INDEX_TYPES:
            raise ValueError(f"index_type '{index_type}' no valido")

        field_names = [field.name for field in table.schema.fields]
        for column in columns:
            if column not in field_names:
                raise ValueError(f"Columna '{column}' no existe en '{table_name}'")

        pk_field = table.schema.get_field(table.schema.primary_key)
        entry = {
            "index": None,
            "type": index_type,
            "columns": columns,
            "rel_oid": self._allocate_oid(),
            "storage_name": index_name,
        }

        if index_type in self.SPATIAL_INDEX_TYPES:
            sp_schema = Schema(table.schema.fields, table.schema.primary_key)
            entry["index"] = self._build_index(table_name, index_name, sp_schema, index_type, columns, secondary=True)
            table.spatial_indexes[index_name] = entry
            self._populate_spatial_index(table, entry)
        else:
            key_field = table.schema.get_field(columns[0])
            sec_schema = Schema([key_field, pk_field], primary_key=columns[0])
            entry["index"] = self._build_index(table_name, index_name, sec_schema, index_type, columns, secondary=True)
            table.secondary_indexes[index_name] = entry
            self._populate_secondary_index(table, entry)

        self._save_catalogs()

    CONTENT_INDEX_TYPES = {"inverted", "multimedia"}

    def add_content_index(
        self,
        table_name: str,
        index_name: str,
        columns: list,
        index_type: str,
        codebook_size: int = 256,
    ) -> dict:
        """Construye un indice de recuperacion por contenido sobre las filas actuales.

        - inverted   : indice invertido de TEXTO (SPIMI + coseno) sobre una columna TEXT.
        - multimedia : Bag of Visual/Acoustic Words + KNN sobre una columna IMAGE/AUDIO.

        El doc_id de cada item es el valor de la clave primaria de la fila.
        Devuelve un pequeno resumen (conteo de items indexados).
        """
        table = self.get_table(table_name)
        used = set(table.secondary_indexes) | set(table.spatial_indexes) | set(table.content_indexes)
        if index_name in used:
            raise ValueError(f"Ya existe un indice llamado '{index_name}' en '{table_name}'")
        if index_type not in self.CONTENT_INDEX_TYPES:
            raise ValueError(f"index_type de contenido invalido: '{index_type}'")

        column = columns[0]
        column_type = next(
            (c["type"].upper() for c in table.column_definitions if c["name"] == column),
            None,
        )
        index_dir = self._index_base_path(table_name, index_name)  # se usa como carpeta
        pk = table.schema.primary_key

        # Reune (doc_id, valor_columna) de todas las filas ya cargadas.
        rows = [
            (item["record"][pk], item["record"].get(column))
            for item in table.index.iter_record_refs()
        ]

        if index_type == "inverted":
            from ..retrieval.text.text_retriever import TextRetriever
            from ..retrieval.text.tokenizer import Tokenizer
            from ..retrieval.text.chunker import Chunker

            retriever = TextRetriever.build(
                ((doc_id, text or "") for doc_id, text in rows),
                index_dir,
                Tokenizer(),
                chunker=Chunker(),
            )
            count = len(rows)
        else:  # multimedia
            from ..retrieval.media.media_retriever import MediaRetriever
            if column_type == "IMAGE":
                from ..retrieval.media.extractors.image_descriptor import ImageDescriptorExtractor
                extractor = ImageDescriptorExtractor()
            else:
                from ..retrieval.media.extractors.audio_descriptor import AudioDescriptorExtractor
                extractor = AudioDescriptorExtractor()
            items = [(doc_id, path) for doc_id, path in rows if path]
            retriever = MediaRetriever.build(items, index_dir, extractor, k=codebook_size)
            count = len(items)

        table.content_indexes[index_name] = {
            "retriever": retriever,
            "type": index_type,
            "columns": columns,
            "storage_name": index_name,
            "rel_oid": self._allocate_oid(),
        }
        self._save_catalogs()
        return {"indexed_items": count, "index": index_name, "type": index_type}

    def drop_secondary_index(self, table_name: str, index_name: str) -> None:
        table = self.get_table(table_name)
        if index_name in table.secondary_indexes:
            del table.secondary_indexes[index_name]
        elif index_name in table.spatial_indexes:
            del table.spatial_indexes[index_name]
        elif index_name in table.content_indexes:
            del table.content_indexes[index_name]
        else:
            raise KeyError(f"Indice '{index_name}' no existe en '{table_name}'")
        self._delete_index_files(table_name, index_name)
        self._save_catalogs()

    def drop_table(self, name: str) -> None:
        if name not in self._tables:
            raise KeyError(f"Tabla '{name}' no existe")

        self._delete_table_files(name)
        del self._tables[name]
        self._save_catalogs()

    def list_tables(self) -> list:
        return list(self._tables.keys())

    # ------------------------------------------------------------------
    # Metodos internos
    # ------------------------------------------------------------------

    def _index_base_path(self, table_name: str, index_name: str) -> str:
        return os.path.join(DATA_DIR, f"{table_name}_{index_name}")

    def _primary_storage_name(self, primary_key_column: str) -> str:
        return f"pk_{primary_key_column}"

    def _primary_index_rel_name(self, table_name: str, primary_key_column: str) -> str:
        return f"pk_{table_name}_{primary_key_column}"

    def _primary_constraint_name(self, table_name: str) -> str:
        return f"{table_name}_pkey"

    def _ensure_data_dir(self) -> None:
        os.makedirs(DATA_DIR, exist_ok=True)
        os.makedirs(CATALOG_DIR, exist_ok=True)

    def _delete_table_files(self, table_name: str) -> None:
        prefix = f"{table_name}_"
        for filename in os.listdir(DATA_DIR):
            if filename.startswith(prefix):
                filepath = os.path.join(DATA_DIR, filename)
                try:
                    if os.path.isdir(filepath):
                        shutil.rmtree(filepath)
                    elif os.path.isfile(filepath):
                        os.remove(filepath)
                except OSError:
                    pass

    def _delete_index_files(self, table_name: str, storage_name: str) -> None:
        base_name = f"{table_name}_{storage_name}"
        extensions = [".bin", "_aux.bin", "_dir.bin", ".root"]
        for ext in extensions:
            filepath = os.path.join(DATA_DIR, base_name + ext)
            if os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except OSError:
                    pass
        dirpath = os.path.join(DATA_DIR, base_name)
        if os.path.isdir(dirpath):
            try:
                shutil.rmtree(dirpath)
            except OSError:
                pass

    def _build_index(
        self,
        table_name: str,
        storage_name: str,
        schema: Schema,
        index_type: str,
        index_columns: list | None = None,
        stats: DiskStats = None,
        secondary: bool = False,
    ):
        if stats is None:
            stats = self.stats
        base_path = self._index_base_path(table_name, storage_name)
        main_path = f"{base_path}.bin"
        pm = PageManager(main_path, stats)

        if index_type == "sequential":
            aux_pm = PageManager(f"{base_path}_aux.bin", stats)
            return SequentialFile(schema, pm, aux_pm, stats)

        if index_type == "hashing":
            dir_pm = PageManager(f"{base_path}_dir.bin", stats)
            return ExtendibleHashing(schema, pm, dir_pm, stats)

        if index_type == "bplus":
            return BPlusTree(schema, pm, stats, clustered=not secondary)

        if index_type == "rtree":
            if index_columns is None or len(index_columns) != 2:
                raise ValueError("RTree requiere exactamente dos columnas para construirse")
            return RTree(schema, pm, stats, index_columns[0], index_columns[1])

        raise ValueError(f"index_type '{index_type}' no valido")

    def _populate_secondary_index(self, table: Table, secondary_entry: dict) -> None:
        from ..indexes.base_index import DuplicateKeyError

        sec_index = secondary_entry["index"]
        column_name = secondary_entry["columns"][0]
        for item in table.index.iter_record_refs():
            record = item["record"]
            try:
                sec_index.add_ref(record[column_name], record[table.schema.primary_key])
            except DuplicateKeyError:
                pass

    def _populate_spatial_index(self, table: Table, spatial_entry: dict) -> None:
        lat_column, lon_column = spatial_entry["columns"]
        refs = []
        for item in table.index.iter_record_refs():
            record = item["record"]
            refs.append(
                {
                    "lat": float(record[lat_column]),
                    "lon": float(record[lon_column]),
                    "pk": record[table.schema.primary_key],
                }
            )
        spatial_entry["index"].build_from_refs(refs)

    def resolve_primary_key(self, table: Table, primary_key_value) -> dict:
        return table.index.search(primary_key_value)

    def find_primary_ref(self, table: Table, key):
        return table.index.find_record_ref(key)

    def _load_csv(self, table: Table, filepath: str) -> int:
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"CSV no encontrado: {filepath}")

        from ..indexes.base_index import DuplicateKeyError
        count = 0
        with open(filepath, newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                record = self._cast_row(row, table.schema)
                table.index.add(record)
                pk_value = record[table.schema.primary_key]
                for sec_entry in table.secondary_indexes.values():
                    try:
                        col = sec_entry["columns"][0]
                        sec_entry["index"].add_ref(record[col], pk_value)
                    except DuplicateKeyError:
                        pass
                for sp_entry in table.spatial_indexes.values():
                    lat_col, lon_col = sp_entry["columns"]
                    sp_entry["index"].add_ref(
                        float(record[lat_col]),
                        float(record[lon_col]),
                        pk_value,
                    )
                count += 1
        return count

    def _cast_row(self, row: dict, schema: Schema) -> dict:
        record = {}
        for field in schema.fields:
            raw = row.get(field.name, "")
            if field.field_type == FieldType.INT:
                record[field.name] = int(raw)
            elif field.field_type == FieldType.FLOAT:
                record[field.name] = float(raw)
            elif field.field_type == FieldType.BOOL:
                record[field.name] = raw.strip().lower() in ("true", "1", "yes", "si")
            else:
                record[field.name] = raw
        return record

    def _load_catalogs(self) -> None:
        self._catalog_meta = self._read_json_file(CATALOG_META_PATH, {"next_oid": DEFAULT_NEXT_OID})
        if "next_oid" not in self._catalog_meta:
            self._catalog_meta["next_oid"] = DEFAULT_NEXT_OID
        self._load_system_catalogs()

    def _load_system_catalogs(self) -> None:
        pg_class = self._read_json_file(PG_CLASS_PATH, [])
        pg_attribute = self._read_json_file(PG_ATTRIBUTE_PATH, [])
        pg_index = self._read_json_file(PG_INDEX_PATH, [])
        pg_constraint = self._read_json_file(PG_CONSTRAINT_PATH, [])

        class_by_oid = {entry["oid"]: entry for entry in pg_class}
        attrs_by_rel_id: dict[int, list] = {}
        for attr in pg_attribute:
            attrs_by_rel_id.setdefault(attr["att_rel_id"], []).append(attr)
        for attrs in attrs_by_rel_id.values():
            attrs.sort(key=lambda item: item["att_num"])

        indexes_by_rel_id: dict[int, list] = {}
        for index_entry in pg_index:
            indexes_by_rel_id.setdefault(index_entry["ind_rel_id"], []).append(index_entry)

        constraints_by_rel_id: dict[int, list] = {}
        for constraint in pg_constraint:
            constraints_by_rel_id.setdefault(constraint["con_rel_id"], []).append(constraint)

        table_entries = [entry for entry in pg_class if entry["rel_kind"] == "table"]
        table_entries.sort(key=lambda entry: entry["oid"])

        for table_entry in table_entries:
            try:
                rel_oid = table_entry["oid"]
                table_name = table_entry["rel_name"]
                attr_rows = attrs_by_rel_id[rel_oid]
                attnum_to_name = {attr["att_num"]: attr["att_name"] for attr in attr_rows}
                column_definitions = [self._column_definition_from_attribute(attr) for attr in attr_rows]

                constraints = constraints_by_rel_id.get(rel_oid, [])
                primary_constraint = next(
                    constraint
                    for constraint in constraints
                    if constraint["con_type"] == "primary_key"
                )
                primary_key_attnum = primary_constraint["con_key"][0]
                primary_key_column = attnum_to_name[primary_key_attnum]

                index_entries = indexes_by_rel_id.get(rel_oid, [])
                primary_index_entry = next(
                    index_entry for index_entry in index_entries if index_entry["ind_is_primary"]
                )
                primary_index_class = class_by_oid[primary_index_entry["index_rel_id"]]
                primary_index_type = primary_index_entry["ind_class"]
                primary_storage_name = self._storage_name_from_file_node(
                    table_name,
                    primary_index_class["rel_file_node"],
                )

                schema = self.schema_from_catalog_columns(column_definitions, primary_key_column)
                primary_index = self._build_index(
                    table_name,
                    primary_storage_name,
                    schema,
                    primary_index_type,
                    [primary_key_column],
                )
                table = Table(
                    table_name,
                    schema,
                    primary_index,
                    column_definitions,
                    primary_index_type,
                    rel_oid=rel_oid,
                    primary_index_oid=primary_index_entry["index_rel_id"],
                    primary_index_name=primary_index_class["rel_name"],
                    primary_constraint_name=primary_constraint["con_name"],
                )

                for index_entry in index_entries:
                    if index_entry["ind_is_primary"]:
                        continue
                    index_class = class_by_oid[index_entry["index_rel_id"]]
                    columns = [attnum_to_name[att_num] for att_num in index_entry["ind_key"]]
                    storage_name = self._storage_name_from_file_node(
                        table_name,
                        index_class["rel_file_node"],
                    )
                    is_spatial = (
                        index_entry.get("ind_is_spatial", False)
                        or index_entry["ind_class"] in self.SPATIAL_INDEX_TYPES
                    )
                    if is_spatial:
                        sp_schema = Schema(schema.fields, schema.primary_key)
                        sp_index = self._build_index(
                            table_name, storage_name, sp_schema,
                            index_entry["ind_class"], columns,
                        )
                        table.spatial_indexes[index_class["rel_name"]] = {
                            "index": sp_index,
                            "type": index_entry["ind_class"],
                            "columns": columns,
                            "rel_oid": index_class["oid"],
                            "storage_name": storage_name,
                        }
                    elif index_entry.get("ind_is_content", False) or index_entry["ind_class"] in self.CONTENT_INDEX_TYPES:
                        table.content_indexes[index_class["rel_name"]] = {
                            "retriever": self._open_content_index(
                                table_name, storage_name, columns, index_entry["ind_class"], column_definitions,
                            ),
                            "type": index_entry["ind_class"],
                            "columns": columns,
                            "rel_oid": index_class["oid"],
                            "storage_name": storage_name,
                        }
                    else:
                        sec_schema = Schema(
                            [schema.get_field(columns[0]), schema.get_field(schema.primary_key)],
                            primary_key=columns[0],
                        )
                        sec_index = self._build_index(
                            table_name, storage_name, sec_schema,
                            index_entry["ind_class"], columns,
                        )
                        table.secondary_indexes[index_class["rel_name"]] = {
                            "index": sec_index,
                            "type": index_entry["ind_class"],
                            "columns": columns,
                            "rel_oid": index_class["oid"],
                            "storage_name": storage_name,
                        }

                self._tables[table_name] = table
            except Exception as exc:
                import warnings
                warnings.warn(
                    f"[catalog] No se pudo cargar la tabla '{table_entry.get('rel_name', '?')}': {exc}",
                    stacklevel=2,
                )
                continue

    def _save_catalogs(self) -> None:
        pg_class = []
        pg_attribute = []
        pg_index = []
        pg_constraint = []

        for table in sorted(self._tables.values(), key=lambda item: item.name):
            if table.rel_oid is None:
                table.rel_oid = self._allocate_oid()
            if table.primary_index_oid is None:
                table.primary_index_oid = self._allocate_oid()
            if table.primary_index_name is None:
                table.primary_index_name = self._primary_index_rel_name(table.name, table.schema.primary_key)
            if table.primary_constraint_name is None:
                table.primary_constraint_name = self._primary_constraint_name(table.name)

            column_number_by_name = {
                column["name"]: position
                for position, column in enumerate(table.column_definitions, start=1)
            }
            primary_storage_name = self._primary_storage_name(table.schema.primary_key)
            primary_file_node = self._index_file_node(table.name, primary_storage_name)

            pg_class.append(
                {
                    "oid": table.rel_oid,
                    "rel_name": table.name,
                    "rel_kind": "table",
                    "rel_natts": len(table.column_definitions),
                    "rel_am": table.primary_index_type,
                    "rel_file_node": primary_file_node,
                }
            )

            for att_num, column in enumerate(table.column_definitions, start=1):
                pg_attribute.append(
                    {
                        "att_rel_id": table.rel_oid,
                        "att_num": att_num,
                        "att_name": column["name"],
                        "att_type": column["type"],
                        "att_len": self._column_length(column),
                        "att_is_primary": column["name"] == table.schema.primary_key,
                    }
                )

            pg_class.append(
                {
                    "oid": table.primary_index_oid,
                    "rel_name": table.primary_index_name,
                    "rel_kind": "index",
                    "rel_natts": 1,
                    "rel_am": table.primary_index_type,
                    "rel_file_node": primary_file_node,
                }
            )
            pg_index.append(
                {
                    "index_rel_id": table.primary_index_oid,
                    "ind_rel_id": table.rel_oid,
                    "ind_is_primary": True,
                    "ind_is_unique": True,
                    "ind_key": [column_number_by_name[table.schema.primary_key]],
                    "ind_class": table.primary_index_type,
                }
            )
            pg_constraint.append(
                {
                    "con_name": table.primary_constraint_name,
                    "con_type": "primary_key",
                    "con_rel_id": table.rel_oid,
                    "con_ind_id": table.primary_index_oid,
                    "con_key": [column_number_by_name[table.schema.primary_key]],
                }
            )

            for index_name, meta in sorted(table.secondary_indexes.items()):
                if meta.get("rel_oid") is None:
                    meta["rel_oid"] = self._allocate_oid()
                if meta.get("storage_name") is None:
                    meta["storage_name"] = index_name

                pg_class.append(
                    {
                        "oid": meta["rel_oid"],
                        "rel_name": index_name,
                        "rel_kind": "index",
                        "rel_natts": len(meta["columns"]),
                        "rel_am": meta["type"],
                        "rel_file_node": self._index_file_node(table.name, meta["storage_name"]),
                    }
                )
                pg_index.append(
                    {
                        "index_rel_id": meta["rel_oid"],
                        "ind_rel_id": table.rel_oid,
                        "ind_is_primary": False,
                        "ind_is_unique": False,
                        "ind_is_spatial": False,
                        "ind_key": [column_number_by_name[column] for column in meta["columns"]],
                        "ind_class": meta["type"],
                    }
                )

            for index_name, meta in sorted(table.spatial_indexes.items()):
                if meta.get("rel_oid") is None:
                    meta["rel_oid"] = self._allocate_oid()
                if meta.get("storage_name") is None:
                    meta["storage_name"] = index_name

                pg_class.append(
                    {
                        "oid": meta["rel_oid"],
                        "rel_name": index_name,
                        "rel_kind": "index",
                        "rel_natts": len(meta["columns"]),
                        "rel_am": meta["type"],
                        "rel_file_node": self._index_file_node(table.name, meta["storage_name"]),
                    }
                )
                pg_index.append(
                    {
                        "index_rel_id": meta["rel_oid"],
                        "ind_rel_id": table.rel_oid,
                        "ind_is_primary": False,
                        "ind_is_unique": False,
                        "ind_is_spatial": True,
                        "ind_key": [column_number_by_name[column] for column in meta["columns"]],
                        "ind_class": meta["type"],
                    }
                )

            for index_name, meta in sorted(table.content_indexes.items()):
                if meta.get("rel_oid") is None:
                    meta["rel_oid"] = self._allocate_oid()
                if meta.get("storage_name") is None:
                    meta["storage_name"] = index_name

                pg_class.append(
                    {
                        "oid": meta["rel_oid"],
                        "rel_name": index_name,
                        "rel_kind": "index",
                        "rel_natts": len(meta["columns"]),
                        "rel_am": meta["type"],
                        "rel_file_node": self._index_file_node(table.name, meta["storage_name"]),
                    }
                )
                pg_index.append(
                    {
                        "index_rel_id": meta["rel_oid"],
                        "ind_rel_id": table.rel_oid,
                        "ind_is_primary": False,
                        "ind_is_unique": False,
                        "ind_is_spatial": False,
                        "ind_is_content": True,
                        "ind_key": [column_number_by_name[column] for column in meta["columns"]],
                        "ind_class": meta["type"],
                    }
                )

        pg_class.sort(key=lambda entry: entry["oid"])
        pg_attribute.sort(key=lambda entry: (entry["att_rel_id"], entry["att_num"]))
        pg_index.sort(key=lambda entry: entry["index_rel_id"])
        pg_constraint.sort(key=lambda entry: (entry["con_rel_id"], entry["con_name"]))

        self._write_json_file(PG_CLASS_PATH, pg_class)
        self._write_json_file(PG_ATTRIBUTE_PATH, pg_attribute)
        self._write_json_file(PG_INDEX_PATH, pg_index)
        self._write_json_file(PG_CONSTRAINT_PATH, pg_constraint)
        self._write_json_file(CATALOG_META_PATH, self._catalog_meta)

    def _index_file_node(self, table_name: str, storage_name: str) -> str:
        return f"{table_name}_{storage_name}"

    def _storage_name_from_file_node(self, table_name: str, rel_file_node: str) -> str:
        prefix = f"{table_name}_"
        if rel_file_node.startswith(prefix):
            return rel_file_node[len(prefix):]
        return rel_file_node

    def _allocate_oid(self) -> int:
        oid = self._catalog_meta["next_oid"]
        self._catalog_meta["next_oid"] += 1
        return oid

    def _read_json_file(self, path: str, default):
        if not os.path.exists(path):
            return default
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)

    def _write_json_file(self, path: str, payload) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)

    def _column_length(self, column: dict) -> int:
        column_type = column["type"].upper()
        if column_type in {"INT", "INTEGER", "SMALLINT", "BIGINT"}:
            return 4
        if column_type in {"REAL", "DOUBLE PRECISION"}:
            return 8
        if column_type == "BOOLEAN":
            return 1
        if column_type == "DATE":
            return 10
        if column_type == "TIME":
            return 8
        if column_type == "CHAR":
            return column["size"]
        if column_type == "TEXT":
            return 512
        if column_type in {"IMAGE", "AUDIO"}:
            return 255
        raise ValueError(f"Tipo de columna desconocido para longitud: '{column['type']}'")

    def _column_definition_from_attribute(self, attribute: dict) -> dict:
        column = {"name": attribute["att_name"], "type": attribute["att_type"]}
        if attribute["att_type"].upper() == "CHAR":
            column["size"] = attribute["att_len"]
        return column

    def _open_content_index(self, table_name: str, storage_name: str, columns: list,
                            index_type: str, column_definitions: list):
        index_dir = self._index_base_path(table_name, storage_name)
        column = columns[0]
        column_type = next(
            (c["type"].upper() for c in column_definitions if c["name"] == column),
            None,
        )
        if index_type == "inverted":
            from ..retrieval.text.text_retriever import TextRetriever
            from ..retrieval.text.tokenizer import Tokenizer

            return TextRetriever.open(index_dir, Tokenizer())
        if index_type == "multimedia":
            from ..retrieval.media.media_retriever import MediaRetriever

            if column_type == "IMAGE":
                from ..retrieval.media.extractors.image_descriptor import ImageDescriptorExtractor
                extractor = ImageDescriptorExtractor()
            else:
                from ..retrieval.media.extractors.audio_descriptor import AudioDescriptorExtractor
                extractor = AudioDescriptorExtractor()
            return MediaRetriever.open(index_dir, extractor)
        raise ValueError(f"Tipo de indice de contenido desconocido: '{index_type}'")

    def _copy_column_definition(self, column: dict) -> dict:
        copied = {"name": column["name"], "type": column["type"]}
        if "size" in column:
            copied["size"] = column["size"]
        return copied

    def _parse_catalog_index_type(self, index_type: str) -> str:
        normalized = index_type.lower()
        legacy_map = {
            "sequential": "sequential",
            "extensible hashing": "hashing",
            "extendible hashing": "hashing",
            "bplus tree": "bplus",
            "rtree": "rtree",
        }
        if normalized in legacy_map:
            return legacy_map[normalized]
        if normalized not in self.INDEX_TYPES:
            raise ValueError(f"Tipo de indice desconocido en catalogo: '{index_type}'")
        return normalized

    # ------------------------------------------------------------------
    # Utilidad: construir Schema desde el parser o el catalogo
    # ------------------------------------------------------------------

    @staticmethod
    def schema_from_columns(columns: list) -> tuple:
        fields = []
        column_definitions = []
        primary_key = None
        primary_index_type = "bplus"

        for column in columns:
            name = column["name"]
            sql_type = column["type"].upper()

            if column.get("primary_key"):
                primary_key = name
                primary_index_type = column.get("primary_index_type") or "bplus"

            if sql_type in {"INT", "INTEGER", "SMALLINT", "BIGINT"}:
                fields.append(Field(name, FieldType.INT))
                column_definitions.append({"name": name, "type": sql_type})
            elif sql_type in {"REAL", "DOUBLE PRECISION"}:
                fields.append(Field(name, FieldType.FLOAT))
                column_definitions.append({"name": name, "type": sql_type})
            elif sql_type == "BOOLEAN":
                fields.append(Field(name, FieldType.BOOL))
                column_definitions.append({"name": name, "type": sql_type})
            elif sql_type.startswith("CHAR("):
                size = int(sql_type[5:-1])
                fields.append(Field(name, FieldType.VARCHAR, max_length=size))
                column_definitions.append({"name": name, "type": "CHAR", "size": size})
            elif sql_type == "DATE":
                fields.append(Field(name, FieldType.VARCHAR, max_length=10))
                column_definitions.append({"name": name, "type": "DATE"})
            elif sql_type == "TIME":
                fields.append(Field(name, FieldType.VARCHAR, max_length=8))
                column_definitions.append({"name": name, "type": "TIME"})
            elif sql_type == "TEXT":
                # Documento textual: se guarda inline en un VARCHAR amplio.
                fields.append(Field(name, FieldType.VARCHAR, max_length=512))
                column_definitions.append({"name": name, "type": "TEXT"})
            elif sql_type in {"IMAGE", "AUDIO"}:
                # Multimedia: la columna guarda la RUTA del archivo (los descriptores
                # viven en el indice de contenido, no en la fila).
                fields.append(Field(name, FieldType.VARCHAR, max_length=255))
                column_definitions.append({"name": name, "type": sql_type})
            else:
                raise ValueError(f"Tipo SQL desconocido: '{sql_type}'")

        if primary_key is None:
            raise ValueError("CREATE TABLE requiere una columna PRIMARY KEY")

        return Schema(fields, primary_key), column_definitions, primary_index_type

    @staticmethod
    def schema_from_catalog_columns(columns: list, primary_key: str) -> Schema:
        fields = []
        for column in columns:
            column_type = column["type"].upper()
            if column_type in {"INT", "INTEGER", "SMALLINT", "BIGINT"}:
                fields.append(Field(column["name"], FieldType.INT))
            elif column_type in {"REAL", "DOUBLE PRECISION"}:
                fields.append(Field(column["name"], FieldType.FLOAT))
            elif column_type == "BOOLEAN":
                fields.append(Field(column["name"], FieldType.BOOL))
            elif column_type == "CHAR":
                fields.append(Field(column["name"], FieldType.VARCHAR, max_length=column["size"]))
            elif column_type == "DATE":
                fields.append(Field(column["name"], FieldType.VARCHAR, max_length=10))
            elif column_type == "TIME":
                fields.append(Field(column["name"], FieldType.VARCHAR, max_length=8))
            elif column_type == "TEXT":
                fields.append(Field(column["name"], FieldType.VARCHAR, max_length=512))
            elif column_type in {"IMAGE", "AUDIO"}:
                fields.append(Field(column["name"], FieldType.VARCHAR, max_length=255))
            else:
                raise ValueError(f"Tipo de dato invalido en catalogo: '{column['type']}'")
        return Schema(fields, primary_key)
