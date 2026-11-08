import os
import struct
from .disk_stats import DiskStats

PAGE_SIZE = 4096  # 4 KB — tamaño fijo de página


class PageManager:
    """
    Gestiona la lectura y escritura de páginas de tamaño fijo en un archivo binario.

    Cada página ocupa exactamente PAGE_SIZE bytes en disco.
    Página 0 → offset 0, página 1 → offset 4096, etc.

    Todos los índices (SequentialFile, BPlusTree, etc.) usan esta clase
    para acceder a disco. NUNCA cargan el archivo completo en memoria.
    """

    # Cabecera de página: guarda cuántos registros hay en la página
    # 2 bytes (unsigned short) al inicio de cada página
    HEADER_SIZE = 2
    HEADER_FORMAT = ">H"  # big-endian unsigned short

    def __init__(self, filepath: str, stats: DiskStats):
        self.filepath = filepath
        self.stats = stats
        self._ensure_file()

    # ------------------------------------------------------------------
    # Operaciones de bajo nivel
    # ------------------------------------------------------------------

    def read_page(self, page_id: int) -> bytes:
        """Lee PAGE_SIZE bytes de la página indicada. +1 read en stats."""
        with open(self.filepath, "rb") as f:
            f.seek(page_id * PAGE_SIZE)
            data = f.read(PAGE_SIZE)
        self.stats.reads += 1
        # Si la página está al final y es parcial, se rellena con ceros
        return data.ljust(PAGE_SIZE, b"\x00")

    def write_page(self, page_id: int, data: bytes) -> None:
        """Escribe PAGE_SIZE bytes en la página indicada. +1 write en stats."""
        if len(data) > PAGE_SIZE:
            raise ValueError(f"Datos ({len(data)}B) superan PAGE_SIZE ({PAGE_SIZE}B)")
        padded = data.ljust(PAGE_SIZE, b"\x00")
        with open(self.filepath, "r+b") as f:
            f.seek(page_id * PAGE_SIZE)
            f.write(padded)
        self.stats.writes += 1

    def allocate_page(self) -> int:
        """Añade una página vacía al final del archivo. Retorna su page_id."""
        page_id = self.total_pages()
        with open(self.filepath, "ab") as f:
            f.write(b"\x00" * PAGE_SIZE)
        return page_id

    def total_pages(self) -> int:
        return os.path.getsize(self.filepath) // PAGE_SIZE

    # ------------------------------------------------------------------
    # Operaciones de página con cabecera (count de registros)
    # ------------------------------------------------------------------

    def read_record_count(self, page_id: int) -> int:
        """Lee el número de registros almacenados en la página."""
        raw = self.read_page(page_id)
        return struct.unpack(self.HEADER_FORMAT, raw[: self.HEADER_SIZE])[0]

    def write_record_count(self, page_id: int, count: int, page_data: bytes) -> None:
        """Actualiza el contador de registros en la cabecera de la página."""
        header = struct.pack(self.HEADER_FORMAT, count)
        new_page = header + page_data[self.HEADER_SIZE :]
        self.write_page(page_id, new_page)

    def records_per_page(self, record_size: int) -> int:
        """Cuántos registros de `record_size` bytes caben en una página (sin cabecera)."""
        return (PAGE_SIZE - self.HEADER_SIZE) // record_size

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------

    def _ensure_file(self) -> None:
        if not os.path.exists(self.filepath):
            # Crear archivo vacío
            open(self.filepath, "wb").close()

    def delete_file(self) -> None:
        """Elimina el archivo de disco (para DROP TABLE)."""
        if os.path.exists(self.filepath):
            os.remove(self.filepath)

    def __repr__(self):
        return (
            f"PageManager('{self.filepath}', "
            f"{self.total_pages()} páginas, "
            f"reads={self.stats.reads}, writes={self.stats.writes})"
        )
