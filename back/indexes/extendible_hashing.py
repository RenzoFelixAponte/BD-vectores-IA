from .base_index import Index, DuplicateKeyError, NotSupportedError
from ..storage import Schema, PageManager, DiskStats, PAGE_SIZE
import struct
import math


class ExtendibleHashing(Index):
    """
    Hashing extensible con directorio dinamico
    """

    BUCKET_SIZE = 4  # registros maximos por bucket antes de split
    FLAG_ACTIVE = 0x01
    FLAG_DELETED = 0x00

    def __init__(self, schema: Schema, page_manager: PageManager,
                 dir_page_manager: PageManager, stats: DiskStats):
        super().__init__(schema, page_manager, stats)
        self.dir_pm = dir_page_manager  # PageManager del directorio
        self._init_directory()
        self.record_size = schema.record_size
        self.record_with_flag_size = self.record_size + 1  # +1 byte para flag

    def _init_directory(self):
        """Inicializa el directorio si esta vacio."""
        if self.dir_pm.total_pages() == 0:
            global_depth = 1
            bucket_page_id = self.pm.allocate_page()
            self._init_bucket_page(bucket_page_id)

            dir_data = struct.pack(">I", global_depth)
            dir_data += struct.pack(">I", bucket_page_id)
            dir_data += struct.pack(">I", bucket_page_id)
            self.dir_pm.write_page(0, dir_data)

    def add(self, record: dict) -> None:
        """Inserta un registro."""
        key = record[self.schema.primary_key]

        if self.search(key) is not None:
            raise DuplicateKeyError(f"La clave {key} ya existe")

        global_depth, page_ids = self._read_directory()
        bucket_page_id = self._find_bucket_page_id(key, global_depth, page_ids)
        records = self._read_bucket(bucket_page_id)

        found_free = False
        for i, (flag, _) in enumerate(records):
            if flag == self.FLAG_DELETED:
                records[i] = (self.FLAG_ACTIVE, record)
                found_free = True
                break

        if not found_free:
            records.append((self.FLAG_ACTIVE, record))

        if len(records) > self.BUCKET_SIZE:
            self._split_bucket(bucket_page_id, records, global_depth, page_ids)
        else:
            self._write_bucket(bucket_page_id, records)

    def search(self, key) -> dict | None:
        """Busqueda exacta por clave."""
        global_depth, page_ids = self._read_directory()
        bucket_page_id = self._find_bucket_page_id(key, global_depth, page_ids)
        records = self._read_bucket(bucket_page_id)

        for flag, record in records:
            if flag == self.FLAG_ACTIVE and record[self.schema.primary_key] == key:
                return record
        return None

    def find_record_ref(self, key):
        global_depth, page_ids = self._read_directory()
        bucket_page_id = self._find_bucket_page_id(key, global_depth, page_ids)
        records = self._read_bucket(bucket_page_id)
        for slot, (flag, record) in enumerate(records):
            if flag == self.FLAG_ACTIVE and record[self.schema.primary_key] == key:
                return {"page_id": bucket_page_id, "slot": slot, "source_id": 0}
        return None

    def add_ref(self, key, primary_key_value) -> None:
        record = {
            self.schema.primary_key: key,
            self.schema.fields[1].name: primary_key_value,
        }
        self.add(record)

    def remove_ref(self, primary_key_value) -> bool:
        pk_field_name = self.schema.fields[1].name
        for item in self.iter_record_refs():
            if item["record"][pk_field_name] == primary_key_value:
                key = item["record"][self.schema.primary_key]
                return self.remove(key)
        return False

    def read_record_ref(self, page_id: int, slot: int, source_id: int = 0) -> dict:
        records = self._read_bucket(page_id)
        if slot < 0 or slot >= len(records):
            raise ValueError("Slot fuera de rango en ExtendibleHashing")
        flag, record = records[slot]
        if flag != self.FLAG_ACTIVE:
            raise ValueError("La referencia apunta a un registro inactivo en ExtendibleHashing")
        return record

    def iter_record_refs(self):
        _, page_ids = self._read_directory()
        for page_id in set(page_ids):
            records = self._read_bucket(page_id)
            for slot, (flag, record) in enumerate(records):
                if flag == self.FLAG_ACTIVE:
                    yield {"record": record, "page_id": page_id, "slot": slot, "source_id": 0}

    def remove(self, key) -> bool:
        """Elimina el registro con esa clave."""
        global_depth, page_ids = self._read_directory()
        bucket_page_id = self._find_bucket_page_id(key, global_depth, page_ids)
        records = self._read_bucket(bucket_page_id)

        for i, (flag, record) in enumerate(records):
            if flag == self.FLAG_ACTIVE and record[self.schema.primary_key] == key:
                records[i] = (self.FLAG_DELETED, record)
                self._write_bucket(bucket_page_id, records)
                return True
        return False

    def range_search(self, begin, end) -> list[dict]:
        """No soportado en hashing extensible."""
        raise NotSupportedError("ExtendibleHashing no soporta range_search")

    def scan_all(self) -> list[dict]:
        """Retorna todos los registros activos iterando los buckets unicos."""
        _, page_ids = self._read_directory()
        results = []
        for page_id in set(page_ids):
            for flag, record in self._read_bucket(page_id):
                if flag == self.FLAG_ACTIVE:
                    results.append(record)
        return results

    # ------------------------------------------------------------------
    # Metodos internos
    # ------------------------------------------------------------------
    def _init_bucket_page(self, page_id: int):
        """Inicializa una pagina de bucket vacia."""
        self.pm.write_record_count(page_id, 0, b"")

    def _hash(self, key, depth: int) -> int:
        """
        Retorna los `depth` bits menos significativos del hash de key.
        """
        hash_val = hash(key) & 0x7fffffff
        mask = (1 << depth) - 1
        return hash_val & mask

    def _read_directory(self):
        """
        Lee el directorio desde disco.
        Retorna: (global_depth, list_page_ids)
        """
        if self.dir_pm.total_pages() == 0:
            return 0, []

        raw = self.dir_pm.read_page(0)
        global_depth = struct.unpack(">I", raw[:4])[0]

        num_entries = 1 << global_depth
        page_ids = []
        for i in range(num_entries):
            offset = 4 + (i * 4)
            page_id = struct.unpack(">I", raw[offset:offset + 4])[0]
            page_ids.append(page_id)

        return global_depth, page_ids

    def _write_directory(self, global_depth: int, page_ids: list):
        """
        Escribe el directorio en disco.
        """
        dir_data = struct.pack(">I", global_depth)
        for page_id in page_ids:
            dir_data += struct.pack(">I", page_id)

        if len(dir_data) < PAGE_SIZE:
            dir_data += b"\x00" * (PAGE_SIZE - len(dir_data))

        self.dir_pm.write_page(0, dir_data)

    def _find_bucket_page_id(self, key, global_depth: int, page_ids: list) -> int:
        """Retorna el page_id del bucket para la clave dada."""
        hash_bits = self._hash(key, global_depth)
        return page_ids[hash_bits]

    def _read_bucket(self, page_id: int) -> list[tuple]:
        """
        Lee un bucket y retorna lista de (flag, record_dict)
        flag = 0x01 activo, 0x00 eliminado
        """
        raw = self.pm.read_page(page_id)
        count = struct.unpack(">H", raw[:2])[0]

        records = []
        offset = 2

        for _ in range(count):
            flag = raw[offset]
            offset += 1
            record_data = raw[offset:offset + self.record_size]
            offset += self.record_size
            record = self.schema.deserialize(record_data)
            records.append((flag, record))

        return records

    def _write_bucket(self, page_id: int, records: list[tuple]):
        """
        Escribe un bucket en disco.
        records: lista de (flag, record_dict)
        """
        data = bytearray()
        count = len(records)

        for flag, record in records:
            data.append(flag)
            data.extend(self.schema.serialize(record))

        full_page = struct.pack(">H", count) + bytes(data)
        full_page = full_page.ljust(PAGE_SIZE, b"\x00")
        self.pm.write_page(page_id, full_page)

    def _split_bucket(self, bucket_page_id: int, records: list, global_depth: int, page_ids: list):
        """
        Divide el bucket y redistribuye sus registros.
        """
        indices = []
        for i, pid in enumerate(page_ids):
            if pid == bucket_page_id:
                indices.append(i)

        num_sharing = len(indices)
        local_depth = global_depth - int(math.log2(num_sharing))
        new_local_depth = local_depth + 1

        new_bucket_page_id = self.pm.allocate_page()
        self._init_bucket_page(new_bucket_page_id)

        records_old = []
        records_new = []

        for flag, record in records:
            key = record[self.schema.primary_key]
            hash_bits = self._hash(key, new_local_depth)
            if (hash_bits >> (new_local_depth - 1)) & 1:
                records_new.append((flag, record))
            else:
                records_old.append((flag, record))

        self._write_bucket(bucket_page_id, records_old)
        self._write_bucket(new_bucket_page_id, records_new)

        if new_local_depth > global_depth:
            page_ids = page_ids + page_ids
            global_depth += 1

        split_bit_position = new_local_depth - 1
        for idx, pid in enumerate(page_ids):
            if pid != bucket_page_id:
                continue
            if ((idx >> split_bit_position) & 1) == 1:
                page_ids[idx] = new_bucket_page_id

        self._write_directory(global_depth, page_ids)
