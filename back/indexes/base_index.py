from abc import ABC, abstractmethod
from ..storage import Schema, PageManager, DiskStats


class Index(ABC):
    """
    Contrato que deben cumplir todos los índices.
    El Executor siempre llama a estos métodos sin importar la implementación.
    """

    def __init__(self, schema: Schema, page_manager: PageManager, stats: DiskStats):
        self.schema = schema
        self.pm = page_manager
        self.stats = stats

    @abstractmethod
    def add(self, record: dict) -> None:
        """
        Inserta un registro.
        Input:  record  dict con todos los campos del schema
        Output: None
        Raises: DuplicateKeyError si la clave ya existe
        """
        ...

    @abstractmethod
    def search(self, key) -> dict | None:
        """
        Búsqueda exacta por clave primaria.
        Input:  key     valor de la clave primaria (int, str, etc.)
        Output: dict con el registro, o None si no existe
        """
        ...

    @abstractmethod
    def range_search(self, begin, end) -> list[dict]:
        """
        Búsqueda por rango [begin, end] sobre la clave primaria.
        Input:  begin   valor mínimo (inclusivo)
                end     valor máximo (inclusivo)
        Output: lista de registros que cumplen begin <= key <= end
        Raises: NotSupportedError en ExtendibleHashing
        """
        ...

    @abstractmethod
    def remove(self, key) -> bool:
        """
        Elimina el registro con esa clave.
        Input:  key     valor de la clave primaria
        Output: True si se eliminó, False si no existía
        """
        ...

    def iter_record_refs(self):
        """
        Itera registros del índice primario junto con su referencia física.
        Output por elemento:
            {
                "record": dict,
                "page_id": int,
                "slot": int,
                "source_id": int,
            }
        """
        raise NotSupportedError(f"{type(self).__name__} no soporta iter_record_refs")

    def read_record_ref(self, page_id: int, slot: int, source_id: int = 0) -> dict:
        """
        Recupera un registro físico a partir de una referencia page/slot.
        """
        raise NotSupportedError(f"{type(self).__name__} no soporta read_record_ref")

    def find_record_ref(self, key):
        """
        Retorna la referencia física del registro asociado a la clave.
        """
        raise NotSupportedError(f"{type(self).__name__} no soporta find_record_ref")

    def add_ref(self, key, primary_key_value) -> None:
        """
        Inserta una referencia en el índice secundario.
        """
        raise NotSupportedError(f"{type(self).__name__} no soporta add_ref")

    def remove_ref(self, primary_key_value) -> bool:
        """
        Elimina una referencia del índice secundario.
        """
        raise NotSupportedError(f"{type(self).__name__} no soporta remove_ref")

    def build_from_refs(self, entries: list[dict]) -> None:
        """
        Reconstruye el índice secundario a partir de referencias.
        """
        raise NotSupportedError(f"{type(self).__name__} no soporta build_from_refs")


class DuplicateKeyError(Exception):
    pass


class NotSupportedError(Exception):
    pass
