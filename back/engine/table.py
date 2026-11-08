from ..storage import Schema
from ..indexes import Index


class Table:
    """
    Representa una tabla: schema + el índice que la gestiona.
    El índice es polimórfico → el Executor llama siempre igual.
    """

    def __init__(
        self,
        name: str,
        schema: Schema,
        index: Index,
        column_definitions: list,
        primary_index_type: str,
        rel_oid: int | None = None,
        primary_index_oid: int | None = None,
        primary_index_name: str | None = None,
        primary_constraint_name: str | None = None,
    ):
        self.name = name
        self.schema = schema
        self.index = index  # SequentialFile | ExtendibleHashing | BPlusTree | RTree
        self.column_definitions = column_definitions
        self.primary_index_type = primary_index_type
        self.rel_oid = rel_oid
        self.primary_index_oid = primary_index_oid
        self.primary_index_name = primary_index_name
        self.primary_constraint_name = primary_constraint_name
        self.secondary_indexes: dict[str, dict] = {}  # index_name -> {"index", "type", "columns", "rel_oid", "storage_name"}
        self.spatial_indexes: dict[str, dict] = {}   # index_name -> {"index", "type", "columns", "rel_oid", "storage_name"}
        # Indices de recuperacion por contenido (Proyecto 2):
        #   index_name -> {"retriever", "type": "inverted"|"multimedia", "columns", "storage_name"}
        self.content_indexes: dict[str, dict] = {}

    def __repr__(self):
        return f"Table('{self.name}', {self.schema}, index={type(self.index).__name__})"
