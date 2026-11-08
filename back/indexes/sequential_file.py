from .base_index import Index, DuplicateKeyError
from ..storage import Schema, PageManager, DiskStats
import struct

class SequentialFile(Index):
    """
    Archivo secuencial ordenado por clave primaria con archivo auxiliar
    de desbordamiento. Cuando el auxiliar alcanza K registros se hace
    una reconstrucción física del archivo principal.
    """

    K = 10  # umbral de registros en auxiliar antes de reconstruir
    FLAG_ACTIVE = 0x00    # Registro activo
    FLAG_DELETED = 0xFF   # Registro eliminado
    SOURCE_MAIN = 0
    SOURCE_AUX = 1
    
    def __init__(self, schema: Schema, page_manager: PageManager,
                 aux_page_manager: PageManager, stats: DiskStats):
        super().__init__(schema, page_manager, stats)
        self.aux_pm = aux_page_manager  # PageManager del archivo auxiliar
        self.record_size = schema.record_size
        self.record_with_flag_size = self.record_size + 1  # +1 byte para flag
        self.PAGE_SIZE = 4096  # Mismo valor que en PageManager.PAGE_SIZE
        self.records_per_page = (self.PAGE_SIZE - 2) // self.record_with_flag_size  # 2 bytes para contador
        
        # Contar registros actuales en el auxiliar al iniciar
        self._aux_record_count = self._count_aux_records()

    def add(self, record: dict) -> None:
        """Inserta un registro."""
        key = record[self.schema.primary_key]
        
        # Verificar si ya existe
        if self.search(key) is not None:
            raise DuplicateKeyError(f"La clave {key} ya existe")
        
        # Verificar si podemos insertar directamente en el principal
        target_page = self._binary_search(key)
        total_main_pages = self.pm.total_pages()
        
        if target_page < total_main_pages:
            if self._insert_in_page(self.pm, target_page, record):
                return
        self._add_to_auxiliary(record)
        
        # Verificar si hay que reconstruir
        if self._aux_record_count >= self.K:
            self._rebuild()

    def search(self, key) -> dict | None:
        """Búsqueda exacta por clave."""
        # Buscar en el principal
        target_page = self._binary_search(key)
        total_main_pages = self.pm.total_pages()
        
        # Revisar la página exacta y adyacentes
        pages_to_check = set()
        if target_page < total_main_pages:
            pages_to_check.add(target_page)
        if target_page > 0:
            pages_to_check.add(target_page - 1)
        if target_page + 1 < total_main_pages:
            pages_to_check.add(target_page + 1)
        
        for page_id in pages_to_check:
            result = self._find_key_in_page(self.pm, page_id, key)
            if result:
                idx, flag = result
                if flag == self.FLAG_ACTIVE:
                    records = self._read_page_records(self.pm, page_id)
                    return records[idx][1]
        
        # Buscar en el auxiliar
        for page_id in range(self.aux_pm.total_pages()):
            result = self._find_key_in_page(self.aux_pm, page_id, key)
            if result:
                idx, flag = result
                if flag == self.FLAG_ACTIVE:
                    records = self._read_page_records(self.aux_pm, page_id)
                    return records[idx][1]
        
        return None

    def find_record_ref(self, key):
        target_page = self._binary_search(key)
        total_main_pages = self.pm.total_pages()

        pages_to_check = set()
        if target_page < total_main_pages:
            pages_to_check.add(target_page)
        if target_page > 0:
            pages_to_check.add(target_page - 1)
        if target_page + 1 < total_main_pages:
            pages_to_check.add(target_page + 1)

        for page_id in pages_to_check:
            records = self._read_page_records(self.pm, page_id)
            for slot, (flag, record) in enumerate(records):
                if flag == self.FLAG_ACTIVE and record[self.schema.primary_key] == key:
                    return {"page_id": page_id, "slot": slot, "source_id": self.SOURCE_MAIN}

        for page_id in range(self.aux_pm.total_pages()):
            records = self._read_page_records(self.aux_pm, page_id)
            for slot, (flag, record) in enumerate(records):
                if flag == self.FLAG_ACTIVE and record[self.schema.primary_key] == key:
                    return {"page_id": page_id, "slot": slot, "source_id": self.SOURCE_AUX}

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
        page_manager = self.pm if source_id == self.SOURCE_MAIN else self.aux_pm
        records = self._read_page_records(page_manager, page_id)
        if slot < 0 or slot >= len(records):
            raise ValueError("Slot fuera de rango en SequentialFile")
        flag, record = records[slot]
        if flag != self.FLAG_ACTIVE:
            raise ValueError("La referencia apunta a un registro inactivo en SequentialFile")
        return record

    def iter_record_refs(self):
        for page_id in range(self.pm.total_pages()):
            records = self._read_page_records(self.pm, page_id)
            for slot, (flag, record) in enumerate(records):
                if flag == self.FLAG_ACTIVE:
                    yield {"record": record, "page_id": page_id, "slot": slot, "source_id": self.SOURCE_MAIN}

        for page_id in range(self.aux_pm.total_pages()):
            records = self._read_page_records(self.aux_pm, page_id)
            for slot, (flag, record) in enumerate(records):
                if flag == self.FLAG_ACTIVE:
                    yield {"record": record, "page_id": page_id, "slot": slot, "source_id": self.SOURCE_AUX}

    def range_search(self, begin, end) -> list[dict]:
        results = []
        
        # Encontrar la página inicial en el principal
        start_page = self._binary_search(begin)
        
        # Scannear desde start_page hacia adelante en el principal
        for page_id in range(start_page, self.pm.total_pages()):
            records = self._read_page_records(self.pm, page_id)
            for flag, record in records:
                if flag != self.FLAG_ACTIVE:
                    continue
                key = record[self.schema.primary_key]
                if key > end:
                    break
                if begin <= key <= end:
                    results.append(record)
            else:
                continue
            break
        
        # Buscar en el auxiliar
        for page_id in range(self.aux_pm.total_pages()):
            records = self._read_page_records(self.aux_pm, page_id)
            for flag, record in records:
                if flag != self.FLAG_ACTIVE:
                    continue
                key = record[self.schema.primary_key]
                if begin <= key <= end:
                    results.append(record)
        
        # Ordenar resultados por clave
        results.sort(key=lambda r: r[self.schema.primary_key])
        return results

    def remove(self, key) -> bool:
        """Elimina el registro con esa clave."""
        # Buscar y marcar en el principal
        target_page = self._binary_search(key)
        total_main_pages = self.pm.total_pages()
        
        pages_to_check = set()
        if target_page < total_main_pages:
            pages_to_check.add(target_page)
        if target_page > 0:
            pages_to_check.add(target_page - 1)
        if target_page + 1 < total_main_pages:
            pages_to_check.add(target_page + 1)
        
        for page_id in pages_to_check:
            records = self._read_page_records(self.pm, page_id)
            for i, (flag, record) in enumerate(records):
                if flag == self.FLAG_ACTIVE and record[self.schema.primary_key] == key:
                    records[i] = (self.FLAG_DELETED, record)
                    self._write_page_records(self.pm, page_id, records)
                    return True
        
        # Buscar y marcar en el auxiliar
        for page_id in range(self.aux_pm.total_pages()):
            records = self._read_page_records(self.aux_pm, page_id)
            for i, (flag, record) in enumerate(records):
                if flag == self.FLAG_ACTIVE and record[self.schema.primary_key] == key:
                    records[i] = (self.FLAG_DELETED, record)
                    self._write_page_records(self.aux_pm, page_id, records)
                    self._aux_record_count -= 1
                    return True
        
        return False

    # ------------------------------------------------------------------
    # Métodos auxiliares
    # ------------------------------------------------------------------

    def _count_aux_records(self) -> int:
        """Cuenta cuántos registros (activos + eliminados) hay en el auxiliar."""
        if self.aux_pm.total_pages() == 0:
            return 0
        
        total = 0
        for page_id in range(self.aux_pm.total_pages()):
            count = self.aux_pm.read_record_count(page_id)
            total += count
        return total

    def _read_page_records(self, page_manager: PageManager, page_id: int) -> list[tuple]:
        """
        Lee una página y retorna lista de (flag, record_dict)
        flag: 0x00 = activo, 0xFF = eliminado
        """
        raw = page_manager.read_page(page_id)
        count = struct.unpack(">H", raw[:2])[0]  # 2 bytes para contador
        
        records = []
        offset = 2  # después del contador
        
        for _ in range(count):
            if offset + self.record_with_flag_size > self.PAGE_SIZE:
                break
            flag = raw[offset]
            offset += 1
            record_data = raw[offset:offset + self.record_size]
            offset += self.record_size
            record = self.schema.deserialize(record_data)
            records.append((flag, record))
        
        return records

    def _write_page_records(self, page_manager: PageManager, page_id: int, records: list[tuple]):
        """
        Escribe una lista de registros en una página.
        Cada registro: [flag(1B)][record_bytes]
        """
        data = bytearray()
        for flag, record in records:
            data.append(flag)
            data.extend(self.schema.serialize(record))
        
        full_page = struct.pack(">H", len(records)) + bytes(data)
        full_page = full_page.ljust(self.PAGE_SIZE, b"\x00")
        page_manager.write_page(page_id, full_page)

    def _get_first_active_key_of_page(self, page_manager: PageManager, page_id: int):
        """
        Retorna la primera clave activa de una página, o None si no hay registros activos.
        """
        records = self._read_page_records(page_manager, page_id)
        for flag, record in records:
            if flag == self.FLAG_ACTIVE:
                return record[self.schema.primary_key]
        return None

    def _get_last_active_key_of_page(self, page_manager: PageManager, page_id: int):
        """
        Retorna la última clave activa de una página, o None si no hay registros activos.
        """
        records = self._read_page_records(page_manager, page_id)
        for flag, record in reversed(records):
            if flag == self.FLAG_ACTIVE:
                return record[self.schema.primary_key]
        return None

    def _find_key_in_page(self, page_manager: PageManager, page_id: int, key) -> tuple[int, int] | None:
        """
        Busca una clave en una página específica.
        Retorna (index, flag) si encuentra, None si no.
        """
        records = self._read_page_records(page_manager, page_id)
        for i, (flag, record) in enumerate(records):
            if record[self.schema.primary_key] == key:
                return (i, flag)
        return None

    def _insert_in_page(self, page_manager: PageManager, page_id: int, record: dict) -> bool:
        """
        Inserta un registro en una página (manteniendo orden).
        Retorna True si cupo, False si la página está llena.
        """
        key = record[self.schema.primary_key]
        records = self._read_page_records(page_manager, page_id)
        
        # Buscar posición de inserción (orden ascendente)
        insert_pos = 0
        for i, (flag, rec) in enumerate(records):
            if rec[self.schema.primary_key] > key:
                insert_pos = i
                break
            insert_pos = i + 1
        
        # Verificar si hay espacio
        if len(records) >= self.records_per_page:
            return False
        
        # Insertar en la posición correcta
        records.insert(insert_pos, (self.FLAG_ACTIVE, record))
        self._write_page_records(page_manager, page_id, records)
        return True

    def _add_to_auxiliary(self, record: dict) -> None:
        """Añade un registro al archivo auxiliar"""
        key = record[self.schema.primary_key]
        
        # Verificar si ya existe en el auxiliar
        for page_id in range(self.aux_pm.total_pages()):
            result = self._find_key_in_page(self.aux_pm, page_id, key)
            if result:
                idx, flag = result
                if flag == self.FLAG_ACTIVE:
                    raise DuplicateKeyError(f"La clave {key} ya existe en el auxiliar")
        
        # Buscar página con espacio o crear nueva
        for page_id in range(self.aux_pm.total_pages()):
            records = self._read_page_records(self.aux_pm, page_id)
            if len(records) < self.records_per_page:
                # Agregar al final (solo append)
                records.append((self.FLAG_ACTIVE, record))
                self._write_page_records(self.aux_pm, page_id, records)
                self._aux_record_count += 1
                return
        
        # Crear nueva página
        new_page_id = self.aux_pm.allocate_page()
        self._write_page_records(self.aux_pm, new_page_id, [(self.FLAG_ACTIVE, record)])
        self._aux_record_count += 1

    # ------------------------------------------------------------------
    # Métodos internos
    # ------------------------------------------------------------------

    def _rebuild(self) -> None:
        """Merge de principal + auxiliar"""
        # Recopilar todos los registros activos del principal
        main_records = []
        for page_id in range(self.pm.total_pages()):
            records = self._read_page_records(self.pm, page_id)
            for flag, record in records:
                if flag == self.FLAG_ACTIVE:
                    main_records.append(record)
        
        # Recopilar todos los registros activos del auxiliar
        aux_records = []
        for page_id in range(self.aux_pm.total_pages()):
            records = self._read_page_records(self.aux_pm, page_id)
            for flag, record in records:
                if flag == self.FLAG_ACTIVE:
                    aux_records.append(record)
        
        # Merge y ordenar
        all_records = main_records + aux_records
        all_records.sort(key=lambda r: r[self.schema.primary_key])
        
        # Verificar duplicados
        seen_keys = set()
        for record in all_records:
            key = record[self.schema.primary_key]
            if key in seen_keys:
                raise DuplicateKeyError(f"Clave duplicada {key} encontrada durante rebuild")
            seen_keys.add(key)
        
        # Escribir nuevo archivo principal
        self.pm.delete_file()
        self.pm._ensure_file()
        
        # Escribir registros en páginas ordenadas
        current_page_id = None
        current_records = []
        
        for record in all_records:
            if current_page_id is None:
                current_page_id = self.pm.allocate_page()
            
            current_records.append((self.FLAG_ACTIVE, record))
            
            if len(current_records) >= self.records_per_page:
                self._write_page_records(self.pm, current_page_id, current_records)
                current_page_id = None
                current_records = []
        
        # Escribir última página si tiene registros
        if current_records:
            if current_page_id is None:
                current_page_id = self.pm.allocate_page()
            self._write_page_records(self.pm, current_page_id, current_records)
        
        # Vaciar archivo auxiliar
        self.aux_pm.delete_file()
        self.aux_pm._ensure_file()
        self._aux_record_count = 0
        
    def _binary_search(self, key) -> int:
        """
        Retorna page_id donde debería estar la clave en el archivo principal.
        Si la clave es menor que todas, retorna 0.
        Si es mayor que todas, retorna total_pages.
        """
        total_pages = self.pm.total_pages()
        if total_pages == 0:
            return 0
        
        left = 0
        right = total_pages - 1
        
        while left <= right:
            mid = (left + right) // 2
            first_key = self._get_first_active_key_of_page(self.pm, mid)
            
            if first_key is None:
                # Página sin registros activos, buscar la siguiente con registros
                found = False
                for i in range(mid + 1, total_pages):
                    first_key = self._get_first_active_key_of_page(self.pm, i)
                    if first_key is not None:
                        mid = i
                        found = True
                        break
                if not found:
                    for i in range(mid - 1, -1, -1):
                        first_key = self._get_first_active_key_of_page(self.pm, i)
                        if first_key is not None:
                            mid = i
                            found = True
                            break
                if not found:
                    return 0  # todas las páginas vacías
            
            if key < first_key:
                right = mid - 1
            else:
                last_key = self._get_last_active_key_of_page(self.pm, mid)
                if last_key is not None and key <= last_key:
                    return mid
                left = mid + 1
        
        return left
