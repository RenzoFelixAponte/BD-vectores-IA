class CreateTableNode:
    """CREATE TABLE nombre (col tipo [PRIMARY KEY [USING idx]], ...) [FROM FILE path]"""

    def __init__(self, table_name: str, columns: list, from_file: str = None):
        self.table_name = table_name
        self.columns = columns      # [{"name": str, "type": str, "primary_key": bool, "primary_index_type": str | None}]
        self.from_file = from_file


class DateLiteralNode:
    """Literal tipado DATE 'yyyy-mm-dd'"""

    def __init__(self, value: str):
        self.value = value

    def __str__(self):
        return self.value


class TimeLiteralNode:
    """Literal tipado TIME 'hh:mm:ss'"""

    def __init__(self, value: str):
        self.value = value

    def __str__(self):
        return self.value


class InsertNode:
    """INSERT INTO tabla VALUES (...)"""

    def __init__(self, table_name: str, values: list):
        self.table_name = table_name
        self.values = values


class SelectAllNode:
    """SELECT * FROM tabla"""

    def __init__(self, table_name: str):
        self.table_name = table_name


class SelectEqualNode:
    """SELECT * FROM tabla WHERE col = valor"""

    def __init__(self, table_name: str, column: str, value):
        self.table_name = table_name
        self.column = column
        self.value = value


class SelectComparisonNode:
    """SELECT * FROM tabla WHERE col <op> valor"""

    def __init__(self, table_name: str, column: str, operator: str, value):
        self.table_name = table_name
        self.column = column
        self.operator = operator
        self.value = value


class SelectRangeNode:
    """SELECT * FROM tabla WHERE col BETWEEN v1 AND v2"""

    def __init__(self, table_name: str, column: str, begin, end):
        self.table_name = table_name
        self.column = column
        self.begin = begin
        self.end = end


class SelectPointRadiusNode:
    """SELECT * FROM tabla WHERE col IN (POINT(x, y), RADIUS r)"""

    def __init__(self, table_name: str, column: str, point: tuple, radius: float):
        self.table_name = table_name
        self.column = column
        self.point = point      # (lat, lon)
        self.radius = radius


class SelectKNNNode:
    """SELECT * FROM tabla WHERE col IN (POINT(x, y), K k)"""

    def __init__(self, table_name: str, column: str, point: tuple, k: int):
        self.table_name = table_name
        self.column = column
        self.point = point      # (lat, lon)
        self.k = k


class SelectCountNode:
    """SELECT COUNT(*) FROM tabla [WHERE col = valor]

    Devuelve el número de filas (con filtro de igualdad opcional), sin materializar
    todas las filas.
    """

    def __init__(self, table_name: str, column: str = None, value=None):
        self.table_name = table_name
        self.column = column
        self.value = value


class TextSearchNode:
    """SELECT * FROM tabla WHERE col @@ 'consulta' LIMIT k [USING metodo]

    Recuperacion de texto por similitud de coseno sobre el indice invertido.
    method: None (auto, usa indice si existe) | 'sequential' (scan + coseno) | 'inverted'.
    """

    def __init__(self, table_name: str, column: str, query_text: str, k: int, method: str = None):
        self.table_name = table_name
        self.column = column
        self.query_text = query_text
        self.k = k
        self.method = method


class MediaSearchNode:
    """SELECT * FROM tabla WHERE col <-> 'ruta_consulta' LIMIT k [USING metodo]

    Recuperacion multimedia (imagen/audio) por KNN sobre histogramas Bag of Words.
    method: None (auto) | 'sequential' (KNN secuencial) | 'multimedia' (KNN indexado).
    """

    def __init__(self, table_name: str, column: str, query_path: str, k: int, method: str = None):
        self.table_name = table_name
        self.column = column
        self.query_path = query_path
        self.k = k
        self.method = method


class DeleteNode:
    """DELETE FROM tabla WHERE col = valor"""

    def __init__(self, table_name: str, column: str, value):
        self.table_name = table_name
        self.column = column
        self.value = value


class CreateIndexNode:
    """CREATE INDEX nombre ON tabla (columna[, columna]) USING tecnica"""

    def __init__(self, index_name: str, table_name: str, columns: list[str], index_type: str):
        self.index_name = index_name
        self.table_name = table_name
        self.columns = columns
        self.index_type = index_type


class DropTableNode:
    """DROP TABLE nombre"""

    def __init__(self, table_name: str):
        self.table_name = table_name


class DropIndexNode:
    """DROP INDEX nombre ON tabla"""

    def __init__(self, index_name: str, table_name: str):
        self.index_name = index_name
        self.table_name = table_name


class ImportFileNode:
    """IMPORT FILE 'ruta' INTO tabla"""

    def __init__(self, table_name: str, filepath: str):
        self.table_name = table_name
        self.filepath = filepath
