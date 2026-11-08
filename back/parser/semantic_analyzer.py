import re

from ..engine.database import Database
from .ast_nodes import (
    CreateIndexNode,
    CreateTableNode,
    DateLiteralNode,
    DeleteNode,
    DropIndexNode,
    DropTableNode,
    ImportFileNode,
    InsertNode,
    SelectAllNode,
    SelectComparisonNode,
    SelectEqualNode,
    SelectKNNNode,
    SelectPointRadiusNode,
    SelectRangeNode,
    TimeLiteralNode,
    TextSearchNode,
    MediaSearchNode,
    SelectCountNode,
)

# Tipos de columna de contenido y los indices de recuperacion que admiten.
_CONTENT_TYPES = {"TEXT", "IMAGE", "AUDIO"}
_TEXT_TYPES = {"TEXT"}
_MEDIA_TYPES = {"IMAGE", "AUDIO"}


class SemanticError(Exception):
    pass


class SemanticAnalyzer:
    """
    Verifica que el AST generado por el análisis sintáctico cumpla las reglas semánticas del proyecto.
    """

    def __init__(self, db: Database | None = None):
        self.error_message = ""
        self.db = db if db is not None else Database()


    # ------------------------------------------------------------------------------
    # Función principal de validación semántica.
    # ------------------------------------------------------------------------------
    def validate(self, node) -> bool:
        self.error_message = ""

        if isinstance(node, CreateTableNode):
            return self.validate_create_table_node(node)

        # Verifica el nodo de tipo DROP TABLE.
        if isinstance(node, DropTableNode):
            return self.validate_drop_table_node(node)

        # Verifica el nodo de tipo CREATE INDEX.
        if isinstance(node, CreateIndexNode):
            return self.validate_create_index_node(node)

        # Verifica el nodo de tipo DROP INDEX.
        if isinstance(node, DropIndexNode):
            return self.validate_drop_index_node(node)
        
        # Verifica el nodo de tipo INSERT.
        if isinstance(node, InsertNode):
            return self.validate_insert_node(node)

        # Verifica el nodo de tipo DELETE.
        if isinstance(node, DeleteNode):
            return self.validate_delete_node(node)

        # Verifica el nodo de tipo SELECT.
        if isinstance(node, SelectAllNode):
            return self.validate_select_all_node(node)
        
        # Verifica el nodo de tipo SELECT con igualdad.
        if isinstance(node, SelectEqualNode):
            return self.validate_select_equal_node(node)

        # Verifica el nodo de tipo SELECT con comparación.
        if isinstance(node, SelectComparisonNode):
            return self.validate_select_comparison_node(node)

        # Verifica el nodo de tipo SELECT con rango.
        if isinstance(node, SelectRangeNode):
            return self.validate_select_range_node(node)

        # Verifica el nodo de tipo SELECT con punto y radio.
        if isinstance(node, SelectPointRadiusNode):
            return self.validate_select_point_radius_node(node)

        # Verifica el nodo de tipo SELECT KNN.
        if isinstance(node, SelectKNNNode):
            return self.validate_select_knn_node(node)

        # Verifica el nodo de tipo IMPORT FILE.
        if isinstance(node, ImportFileNode):
            return self.validate_import_file_node(node)

        # Verifica el nodo de busqueda textual por coseno (@@).
        if isinstance(node, TextSearchNode):
            return self.validate_text_search_node(node)

        # Verifica el nodo de busqueda multimedia por KNN (<->).
        if isinstance(node, MediaSearchNode):
            return self.validate_media_search_node(node)

        # Verifica el nodo SELECT COUNT(*).
        if isinstance(node, SelectCountNode):
            if node.column is not None:
                return self.validate_scalar_lookup(node.table_name, node.column)
            if not self.table_exists(node.table_name):
                self.error_message = f"La tabla '{node.table_name}' no existe"
                return False
            return True

        self.error_message = f"No existe verificacion semantica para el nodo {type(node).__name__}"
        return False

    # ------------------------------------------------------------------------------
    # Funciones responsables de verificar cada tipo de nodo específico.
    # ------------------------------------------------------------------------------

    # Verifica que un nodo de tipo CREATE TABLE cumpla las reglas semanticas del proyecto.
    def validate_create_table_node(self, node: CreateTableNode) -> bool:
        
        # Verifica que no exista una tabla con el mismo nombre.
        if self.table_exists(node.table_name):
            self.error_message = f"La tabla '{node.table_name}' ya existe"
            return False

        names = set()
        primary_key_count = 0

        for column in node.columns:
            name = column["name"]
            column_type = column["type"]
            primary_index_type = column.get("primary_index_type")

            # Verifica que no haya columnas repetidas en la misma tabla.
            if name in names:
                self.error_message = f"La columna '{name}' esta repetida en CREATE TABLE"
                return False
            names.add(name)

            if column.get("primary_key"):
                primary_key_count += 1
            elif primary_index_type is not None:
                self.error_message = (f"La columna '{name}' no puede declarar PRIMARY KEY USING sin PRIMARY KEY")
                return False

            # Verifica que si el tipo de columna es CHAR, tenga un tamaño válido.
            if column_type.startswith("CHAR(") and column_type.endswith(")"):
                size = int(column_type[5:-1])
                if size <= 0:
                    self.error_message = "CHAR(n) debe usar un tamano entero mayor que cero"
                    return False

            # Verifica que el tipo de indice para PRIMARY KEY sea válido.
            if primary_index_type not in (None, "bplus", "hashing", "sequential"):
                self.error_message = ("PRIMARY KEY USING solo permite BPLUS TREE, EXTENDIBLE HASHING o SEQUENTIAL FILE")
                return False

        # Verifica que haya exactamente una columna PRIMARY KEY.
        if primary_key_count == 0:
            self.error_message = "CREATE TABLE debe declarar exactamente una columna PRIMARY KEY"
            return False
        elif primary_key_count > 1:
            self.error_message = "CREATE TABLE no puede declarar mas de una columna PRIMARY KEY"
            return False

        # Verifica que si se declara FROM FILE, la ruta no sea vacia.
        if node.from_file is not None and node.from_file == "":
            self.error_message = "FROM FILE debe recibir una ruta no vacia"
            return False

        return True

    # Verifica que un nodo de tipo CREATE INDEX cumpla las reglas semanticas del proyecto.
    def validate_create_index_node(self, node: CreateIndexNode) -> bool:
        
        # Verifica que la tabla sobre la que se quiere crear el indice exista.
        if not self.table_exists(node.table_name):
            self.error_message = f"La tabla '{node.table_name}' no existe"
            return False

        # Verifica que no exista un indice con el mismo nombre en la tabla.
        table = self.db.get_table(node.table_name)
        all_index_names = set(table.secondary_indexes) | set(table.spatial_indexes) | set(table.content_indexes)
        if node.index_name in all_index_names:
            self.error_message = f"Ya existe un indice llamado '{node.index_name}' en '{node.table_name}'"
            return False

        # Verifica que no se repitan columnas en la definición del índice.
        if len(set(node.columns)) != len(node.columns):
            self.error_message = "CREATE INDEX no puede repetir columnas en la misma definicion"
            return False

        # Verifica que las columnas declaradas para el índice existan en la tabla.
        for column in node.columns:
            if not self.column_exists(table, column):
                self.error_message = f"Columna '{column}' no existe en '{node.table_name}'"
                return False

        # Indices de recuperacion por contenido: el tipo de indice debe calzar con
        # el tipo de la columna (INVERTED -> TEXT, MULTIMEDIA -> IMAGE/AUDIO).
        if node.index_type in ("inverted", "multimedia"):
            if len(node.columns) != 1:
                self.error_message = "Un indice de recuperacion por contenido usa exactamente una columna"
                return False
            declared = self.get_declared_column_type(table, node.columns[0])
            if node.index_type == "inverted" and declared not in _TEXT_TYPES:
                self.error_message = "USING INVERTED requiere una columna de tipo TEXT"
                return False
            if node.index_type == "multimedia" and declared not in _MEDIA_TYPES:
                self.error_message = "USING MULTIMEDIA requiere una columna IMAGE o AUDIO"
                return False
            return True

        # Verifica que el tipo de índice sea válido y que la cantidad de columnas sea compatible con el tipo.
        if node.index_type == "rtree":
            if len(node.columns) != 2:
                self.error_message = "CREATE INDEX USING RTREE debe declarar exactamente dos columnas"
                return False
            return True
        elif len(node.columns) != 1:
            self.error_message = "CREATE INDEX escalar debe declarar exactamente una columna"
            return False

        return True
    
    # Verifica que un nodo de tipo INSERT cumpla las reglas semanticas del proyecto.
    def validate_insert_node(self, node: InsertNode) -> bool:
        
        # Verifica que la tabla sobre la que se quiere insertar exista.
        if not self.table_exists(node.table_name):
            self.error_message = f"La tabla '{node.table_name}' no existe"
            return False

        table = self.db.get_table(node.table_name)
        fields = table.schema.fields

        # Verifica que la cantidad de valores a insertar coincida con la cantidad de columnas de la tabla.
        if len(node.values) != len(fields):
            self.error_message = (f"INSERT: se esperaban {len(fields)} valores, se recibieron {len(node.values)}")
            return False

        # Verifica que cada valor a insertar sea compatible con el tipo de su columna correspondiente.
        for field, value in zip(fields, node.values):
            if not self.validate_literal(value):
                return False
            declared_type = self.get_declared_column_type(table, field.name)
            if not self.literal_matches_field(value, declared_type):
                self.error_message = (f"El valor '{self.literal_value(value)}' no es compatible con la columna '{field.name}'")
                return False
        
        return True

    # Verifica que un nodo de tipo SELECT * FROM tabla cumpla las reglas semanticas del proyecto.
    def validate_select_all_node(self, node: SelectAllNode) -> bool:
        
        # Verifica que la tabla sobre la que se quiere consultar exista.
        if not self.table_exists(node.table_name):
            self.error_message = f"La tabla '{node.table_name}' no existe"
            return False
        
        return True

    # Verifica que un nodo de tipo DROP TABLE cumpla las reglas semanticas del proyecto.
    def validate_drop_table_node(self, node: DropTableNode) -> bool:

        # Verifica que la tabla que se quiere eliminar exista.
        if not self.table_exists(node.table_name):
            self.error_message = f"La tabla '{node.table_name}' no existe"
            return False
        
        return True

    # Verifica que un nodo de tipo DROP INDEX cumpla las reglas semanticas del proyecto.
    def validate_drop_index_node(self, node: DropIndexNode) -> bool:

        # Verifica que la tabla exista.
        if not self.table_exists(node.table_name):
            self.error_message = f"La tabla '{node.table_name}' no existe"
            return False

        # Verifica que el índice exista en la tabla (secundario o espacial).
        table = self.db.get_table(node.table_name)
        all_index_names = set(table.secondary_indexes) | set(table.spatial_indexes)
        if node.index_name not in all_index_names:
            self.error_message = f"Indice '{node.index_name}' no existe en '{node.table_name}'"
            return False
        
        return True

    # Verifica que un nodo de tipo SELECT con igualdad cumpla las reglas semanticas del proyecto.
    def validate_select_equal_node(self, node: SelectEqualNode) -> bool:
        
        # Verifica que la tabla y la columna exista.
        if not self.validate_scalar_lookup(node.table_name, node.column):
            return False
        
        # Verifica que el valor a comparar tenga el formato correcto para literales de tipo DATE o TIME.
        if not self.validate_literal(node.value):
            return False
        
        # Verifica que el tipo del valor sea compatible con el tipo de la columna.
        table = self.db.get_table(node.table_name)
        declared_type = self.get_declared_column_type(table, node.column)
        if not self.literal_matches_field(node.value, declared_type):
            self.error_message = (f"El valor '{self.literal_value(node.value)}' no es compatible con la columna '{node.column}'")
            return False
        return True

    # Verifica que un nodo de tipo SELECT con operadores de comparación cumpla las reglas semanticas del proyecto.
    def validate_select_comparison_node(self, node: SelectComparisonNode) -> bool:
        
        # Verifica que la tabla y la columna exista.
        if not self.validate_scalar_lookup(node.table_name, node.column):
            return False
        
        # Verifica que el valor a comparar tenga el formato correcto para literales de tipo DATE o TIME.
        if not self.validate_literal(node.value):
            return False
        
        # Verifica que el tipo del valor sea compatible con el tipo de la columna.
        table = self.db.get_table(node.table_name)
        declared_type = self.get_declared_column_type(table, node.column)
        if not self.literal_matches_field(node.value, declared_type):
            self.error_message = (f"El valor '{self.literal_value(node.value)}' no es compatible con la columna '{node.column}'")
            return False
        
        return True

    # Verifica que un nodo de tipo SELECT con operador BETWEEN cumpla las reglas semanticas del proyecto.
    def validate_select_range_node(self, node: SelectRangeNode) -> bool:
        
        # Verifica que la tabla y la columna exista.
        if not self.validate_scalar_lookup(node.table_name, node.column):
            return False
        
        # Verifica que los valores de los límites tengan el formato correcto para literales de tipo DATE o TIME.
        if not self.validate_literal(node.begin):
            return False
        if not self.validate_literal(node.end):
            return False

        # Verifica que los valores a comparar sean compatibles con el tipo de la columna.
        table = self.db.get_table(node.table_name)
        declared_type = self.get_declared_column_type(table, node.column)
        if not self.literal_matches_field(node.begin, declared_type) or not self.literal_matches_field(node.end, declared_type):
            self.error_message = f"BETWEEN debe usar valores compatibles con la columna '{node.column}'"
            return False

        # Verifica que los tipos de los límites sean compatibles entre sí.
        begin_type = type(node.begin)
        end_type = type(node.end)
        numeric_range = begin_type in (int, float) and end_type in (int, float)
        date_range = isinstance(node.begin, DateLiteralNode) and isinstance(node.end, DateLiteralNode)
        time_range = isinstance(node.begin, TimeLiteralNode) and isinstance(node.end, TimeLiteralNode)
        if begin_type != end_type and not numeric_range and not date_range and not time_range:
            self.error_message = "BETWEEN debe comparar literales compatibles entre si"
            return False

        # Verifica que el límite inferior no sea mayor que el límite superior.
        begin_value = self.literal_value(node.begin)
        end_value = self.literal_value(node.end)
        if begin_value > end_value:
            self.error_message = "BETWEEN debe usar un limite inferior menor o igual al superior"
            return False

        return True

    # Verifica que un nodo de tipo SELECT con POINT y RADIUS cumpla las reglas semanticas del proyecto.
    def validate_select_point_radius_node(self, node: SelectPointRadiusNode) -> bool:
        
        # Verifica que la tabla sobre la que se quiere consultar exista y tenga un índice RTree.
        if not self.validate_spatial_lookup(node.table_name):
            return False

        x = node.point[0]
        y = node.point[1]

        # Verifica que las coordenadas del punto sean numéricas.
        if type(x) not in (int, float) or type(y) not in (int, float):
            self.error_message = "POINT(x, y) debe usar coordenadas numericas"
            return False

        # Verifica que el radio sea un número positivo.
        if type(node.radius) not in (int, float) or node.radius <= 0:
            self.error_message = "RADIUS debe ser un valor numerico positivo"
            return False

        return True

    # Verifica que un nodo de tipo SELECT KNN cumpla las reglas semanticas del proyecto.
    def validate_select_knn_node(self, node: SelectKNNNode) -> bool:
        
        # Verifica que la tabla exista y tenga un índice RTree.
        if not self.validate_spatial_lookup(node.table_name):
            return False

        x = node.point[0]
        y = node.point[1]

        # Verifica que las coordenadas del punto sean numéricas.
        if type(x) not in (int, float) or type(y) not in (int, float):
            self.error_message = "POINT(x, y) debe usar coordenadas numericas"
            return False

        # Verifica que K sea un entero positivo.
        if type(node.k) is not int or node.k <= 0:
            self.error_message = "K debe ser un entero positivo"
            return False

        return True

    # Verifica que un nodo de tipo IMPORT FILE cumpla las reglas semanticas del proyecto.
    def validate_import_file_node(self, node: ImportFileNode) -> bool:

        # Verifica que la tabla destino exista.
        if not self.table_exists(node.table_name):
            self.error_message = f"La tabla '{node.table_name}' no existe"
            return False

        # Verifica que la ruta del archivo no esté vacía.
        if not node.filepath or node.filepath.strip() == "":
            self.error_message = "IMPORT FILE debe recibir una ruta no vacia"
            return False

        return True

    # Verifica que un nodo de tipo DELETE cumpla las reglas semanticas del proyecto.
    def validate_delete_node(self, node: DeleteNode) -> bool:
        
        # Verifica que la tabla y la columna sobre la que se quiere eliminar exista.
        if not self.validate_scalar_lookup(node.table_name, node.column):
            return False
                
        if not self.validate_literal(node.value):
            return False
        
        # Verifica que el valor a comparar sea compatible con el tipo de dato de la columna.
        table = self.db.get_table(node.table_name)
        declared_type = self.get_declared_column_type(table, node.column)
        if not self.literal_matches_field(node.value, declared_type):
            self.error_message = (f"El valor '{self.literal_value(node.value)}' no es compatible con la columna '{node.column}'")
            return False
        
        return True

    # Verifica que un nodo de busqueda textual por coseno (@@) sea valido.
    def validate_text_search_node(self, node: TextSearchNode) -> bool:
        if not self.validate_scalar_lookup(node.table_name, node.column):
            return False

        table = self.db.get_table(node.table_name)
        declared_type = self.get_declared_column_type(table, node.column)
        if declared_type not in _TEXT_TYPES:
            self.error_message = (
                f"El operador @@ requiere una columna TEXT; "
                f"'{node.column}' es de tipo {declared_type}"
            )
            return False

        if type(node.k) is not int or node.k <= 0:
            self.error_message = "LIMIT debe ser un entero positivo"
            return False

        if not node.query_text or node.query_text.strip() == "":
            self.error_message = "La consulta textual no puede estar vacia"
            return False

        return True

    # Verifica que un nodo de busqueda multimedia por KNN (<->) sea valido.
    def validate_media_search_node(self, node: MediaSearchNode) -> bool:
        if not self.validate_scalar_lookup(node.table_name, node.column):
            return False

        table = self.db.get_table(node.table_name)
        declared_type = self.get_declared_column_type(table, node.column)
        if declared_type not in _MEDIA_TYPES:
            self.error_message = (
                f"El operador <-> requiere una columna IMAGE o AUDIO; "
                f"'{node.column}' es de tipo {declared_type}"
            )
            return False

        if type(node.k) is not int or node.k <= 0:
            self.error_message = "LIMIT debe ser un entero positivo"
            return False

        if not node.query_path or node.query_path.strip() == "":
            self.error_message = "La ruta de consulta multimedia no puede estar vacia"
            return False

        return True

    # ------------------------------------------------------------------------------
    # Funciones auxiliares para validación semántica de nodos específicos.
    # ------------------------------------------------------------------------------

    # Verifica que la tabla y la columna existan para una consulta para búsquedas escalares
    def validate_scalar_lookup(self, table_name: str, column_name: str) -> bool:
        if not self.table_exists(table_name):
            self.error_message = f"La tabla '{table_name}' no existe"
            return False
        table = self.db.get_table(table_name)
        if not self.column_exists(table, column_name):
            self.error_message = f"Columna '{column_name}' no existe en '{table_name}'"
            return False
        return True

    # Verifica que la tabla exista y tenga un índice espacial para búsqueda espacial.
    def validate_spatial_lookup(self, table_name: str) -> bool:
        if not self.table_exists(table_name):
            self.error_message = f"La tabla '{table_name}' no existe"
            return False
        table = self.db.get_table(table_name)
        if not table.spatial_indexes:
            self.error_message = f"La tabla '{table_name}' no tiene un indice espacial"
            return False
        return True

    # Verifica si la tabla existe en la base de datos.
    def table_exists(self, table_name: str) -> bool:
        return table_name in self.db.list_tables()

    # Verifica si la columna existe en la tabla de datos especificada.
    def column_exists(self, table, column_name: str) -> bool:
        return any(field.name == column_name for field in table.schema.fields)

    # Verifica que un valor literal tenga el formato correcto.
    def validate_literal(self, value) -> bool:
        if isinstance(value, DateLiteralNode):
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value.value) is None:
                self.error_message = "DATE debe tener el formato semantico yyyy-mm-dd"
                return False

            year, month, day = value.value.split("-")
            year = int(year)
            month = int(month)
            day = int(day)
            if month < 1 or month > 12:
                self.error_message = "DATE debe contener un mes entre 01 y 12"
                return False

            days_in_month = {
                1: 31,
                2: 29 if self.is_leap_year(year) else 28,
                3: 31,
                4: 30,
                5: 31,
                6: 30,
                7: 31,
                8: 31,
                9: 30,
                10: 31,
                11: 30,
                12: 31,
            }
            if day < 1 or day > days_in_month[month]:
                self.error_message = "DATE debe contener un dia valido para el mes y ano indicados"
                return False

        if isinstance(value, TimeLiteralNode):
            if re.fullmatch(r"\d{2}:\d{2}:\d{2}", value.value) is None:
                self.error_message = "TIME debe tener el formato semantico hh:mm:ss"
                return False

            hour, minute, second = value.value.split(":")
            hour = int(hour)
            minute = int(minute)
            second = int(second)
            if hour < 0 or hour > 23 or minute < 0 or minute > 59 or second < 0 or second > 59:
                self.error_message = "TIME debe contener hora, minuto y segundo dentro de rangos validos"
                return False

        return True

    # Retorna el tipo declarado de una columna en la tabla de datos especificada.
    def get_declared_column_type(self, table, column_name: str) -> str:
        for column in table.column_definitions:
            if column["name"] == column_name:
                return column["type"].upper()
        raise KeyError(f"Columna '{column_name}' no existe en '{table.name}'")

    # Verifica que un valor del literal sea compatible con el tipo de dato de la columna.
    def literal_matches_field(self, value, declared_type: str) -> bool:
        if declared_type in {"INT", "INTEGER", "SMALLINT", "BIGINT"}:
            return type(value) is int
        if declared_type in {"REAL", "DOUBLE PRECISION"}:
            return type(value) in (int, float)
        if declared_type == "BOOLEAN":
            return type(value) is bool
        if declared_type == "DATE":
            return isinstance(value, DateLiteralNode)
        if declared_type == "TIME":
            return isinstance(value, TimeLiteralNode)
        if declared_type == "CHAR":
            return type(value) is str
        return True

    # Retorna el valor del literal
    def literal_value(self, value):
        if isinstance(value, (DateLiteralNode, TimeLiteralNode)):
            return value.value
        return value

    # Determina si un año es bisiesto.
    def is_leap_year(self, year: int) -> bool:
        if year % 400 == 0:
            return True
        if year % 100 == 0:
            return False
        return year % 4 == 0
