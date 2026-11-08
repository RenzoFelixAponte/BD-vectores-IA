from .lexical_analyzer import Token, TokenType
from .ast_nodes import (
    CreateTableNode, CreateIndexNode, DateLiteralNode, TimeLiteralNode, InsertNode,
    SelectAllNode, SelectEqualNode, SelectComparisonNode, SelectRangeNode,
    SelectPointRadiusNode, SelectKNNNode, DeleteNode, DropTableNode, DropIndexNode,
    ImportFileNode, TextSearchNode, MediaSearchNode, SelectCountNode,
)


class SyntacticError(Exception):
    pass


class SyntacticAnalyzer:
    """
    Responsable del análisis sintáctico del subconjunto SQL del proyecto.
    Recibe la lista de tokens ya generada por el lexer y retorna un nodo AST.
    """

    def __init__(self):
        self.tokens = []
        self.pos = 0

    def parse(self, tokens: list):
        self.tokens = tokens
        self.pos = 0
        tok = self.peek()
        if tok.type == TokenType.CREATE:
            next_tok = self.tokens[self.pos + 1] if self.pos + 1 < len(self.tokens) else None
            if next_tok and next_tok.type == TokenType.INDEX:
                node = self.parse_create_index()
            else:
                node = self.parse_create_table()
        elif tok.type == TokenType.DROP:
            node = self.parse_drop()
        elif tok.type == TokenType.INSERT:
            node = self.parse_insert()
        elif tok.type == TokenType.SELECT:
            node = self.parse_select()
        elif tok.type == TokenType.DELETE:
            node = self.parse_delete()
        elif tok.type == TokenType.IMPORT:
            node = self.parse_import_file()
        else:
            raise SyntacticError(f"Sentencia desconocida: '{tok.value}' en línea {tok.line}")
        self.expect(TokenType.SEMICOLON)
        self.expect(TokenType.EOF)
        return node

    def parse_drop(self):
        self.expect(TokenType.DROP)
        next_tok = self.peek()

        if next_tok.type == TokenType.TABLE:
            self.advance()
            table_name = self.expect(TokenType.IDENTIFIER).value
            return DropTableNode(table_name)

        if next_tok.type == TokenType.INDEX:
            self.advance()
            index_name = self.expect(TokenType.IDENTIFIER).value
            self.expect(TokenType.ON)
            table_name = self.expect(TokenType.IDENTIFIER).value
            return DropIndexNode(index_name, table_name)

        raise SyntacticError(
            f"Se esperaba TABLE o INDEX despues de DROP, se obtuvo '{next_tok.value}' "
            f"en linea {next_tok.line}"
        )

    def parse_create_table(self) -> CreateTableNode:
        self.expect(TokenType.CREATE)
        self.expect(TokenType.TABLE)
        name = self.expect(TokenType.IDENTIFIER).value
        self.expect(TokenType.LEFT_PARENTHESIS)

        columns = []
        while True:
            col_name = self.expect(TokenType.IDENTIFIER).value
            col_type = self.read_column_type()
            primary_key = False
            primary_index_type = None
            if self.peek().type == TokenType.PRIMARY:
                self.advance()
                self.expect(TokenType.KEY)
                primary_key = True
                if self.peek().type == TokenType.USING:
                    self.advance()
                    primary_index_type = self.read_primary_index_type()

            columns.append(
                {
                    "name": col_name,
                    "type": col_type,
                    "primary_key": primary_key,
                    "primary_index_type": primary_index_type,
                }
            )

            if self.peek().type == TokenType.COMMA:
                self.advance()
            else:
                break

        self.expect(TokenType.RIGHT_PARENTHESIS)

        from_file = None
        if self.peek().type == TokenType.FROM:
            self.advance()
            self.expect(TokenType.FILE)
            from_file = self.expect(TokenType.STRING_LITERAL).value

        return CreateTableNode(name, columns, from_file)

    def parse_create_index(self) -> CreateIndexNode:
        self.expect(TokenType.CREATE)
        self.expect(TokenType.INDEX)
        index_name = self.expect(TokenType.IDENTIFIER).value
        self.expect(TokenType.ON)
        table_name = self.expect(TokenType.IDENTIFIER).value
        self.expect(TokenType.LEFT_PARENTHESIS)
        columns = [self.expect(TokenType.IDENTIFIER).value]
        if self.peek().type == TokenType.COMMA:
            self.advance()
            columns.append(self.expect(TokenType.IDENTIFIER).value)
        self.expect(TokenType.RIGHT_PARENTHESIS)
        self.expect(TokenType.USING)
        index_type = self.read_index_type()
        return CreateIndexNode(index_name, table_name, columns, index_type)

    def parse_insert(self) -> InsertNode:
        self.expect(TokenType.INSERT)
        self.expect(TokenType.INTO)
        name = self.expect(TokenType.IDENTIFIER).value
        self.expect(TokenType.VALUES)
        self.expect(TokenType.LEFT_PARENTHESIS)

        values = []
        while True:
            values.append(self.read_literal())
            if self.peek().type == TokenType.COMMA:
                self.advance()
            else:
                break

        self.expect(TokenType.RIGHT_PARENTHESIS)
        return InsertNode(name, values)

    def parse_select(self):
        self.expect(TokenType.SELECT)

        # SELECT COUNT(*) FROM tabla [WHERE col = valor]
        if self.peek().type == TokenType.COUNT:
            self.advance()
            self.expect(TokenType.LEFT_PARENTHESIS)
            self.expect(TokenType.ASTERISK)
            self.expect(TokenType.RIGHT_PARENTHESIS)
            self.expect(TokenType.FROM)
            table_name = self.expect(TokenType.IDENTIFIER).value
            if self.peek().type != TokenType.WHERE:
                return SelectCountNode(table_name)
            self.advance()
            col = self.expect(TokenType.IDENTIFIER).value
            self.expect(TokenType.EQUAL)
            value = self.read_literal()
            return SelectCountNode(table_name, col, value)

        self.expect(TokenType.ASTERISK)
        self.expect(TokenType.FROM)
        table_name = self.expect(TokenType.IDENTIFIER).value

        if self.peek().type == TokenType.SEMICOLON:
            return SelectAllNode(table_name)

        self.expect(TokenType.WHERE)
        col = self.expect(TokenType.IDENTIFIER).value

        tok = self.peek()

        # Recuperacion de texto por coseno:  col @@ 'consulta' LIMIT k [USING metodo]
        if tok.type == TokenType.MATCH:
            self.advance()
            query_text = self.expect(TokenType.STRING_LITERAL).value
            k = self.read_limit()
            method = self.read_retrieval_method()
            return TextSearchNode(table_name, col, query_text, k, method)

        # Recuperacion multimedia por KNN:  col <-> 'ruta' LIMIT k [USING metodo]
        if tok.type == TokenType.SIM:
            self.advance()
            query_path = self.expect(TokenType.STRING_LITERAL).value
            k = self.read_limit()
            method = self.read_retrieval_method()
            return MediaSearchNode(table_name, col, query_path, k, method)

        if tok.type == TokenType.EQUAL:
            self.advance()
            value = self.read_literal()
            return SelectEqualNode(table_name, col, value)

        if tok.type in (
            TokenType.LESS_THAN,
            TokenType.GREATER_THAN,
            TokenType.LESS_THAN_OR_EQUAL,
            TokenType.GREATER_THAN_OR_EQUAL,
        ):
            operator = self.advance().value
            value = self.read_literal()
            return SelectComparisonNode(table_name, col, operator, value)

        if tok.type == TokenType.BETWEEN:
            self.advance()
            begin = self.read_literal()
            self.expect(TokenType.AND)
            end = self.read_literal()
            return SelectRangeNode(table_name, col, begin, end)

        if tok.type == TokenType.IN:
            self.advance()
            self.expect(TokenType.LEFT_PARENTHESIS)
            self.expect(TokenType.POINT)
            self.expect(TokenType.LEFT_PARENTHESIS)
            x = self.read_literal()
            self.expect(TokenType.COMMA)
            y = self.read_literal()
            self.expect(TokenType.RIGHT_PARENTHESIS)
            self.expect(TokenType.COMMA)

            next_tok = self.peek()

            if next_tok.type == TokenType.RADIUS:
                self.advance()
                r = self.read_literal()
                self.expect(TokenType.RIGHT_PARENTHESIS)
                return SelectPointRadiusNode(table_name, col, (x, y), float(r))

            if next_tok.type == TokenType.K:
                self.advance()
                k = self.expect(TokenType.INTEGER_LITERAL).value
                self.expect(TokenType.RIGHT_PARENTHESIS)
                return SelectKNNNode(table_name, col, (x, y), k)

            raise SyntacticError(
                f"Se esperaba RADIUS o K, se obtuvo '{next_tok.value}' "
                f"en línea {next_tok.line}"
            )

        raise SyntacticError(
            f"Operador WHERE desconocido: '{tok.value}' en línea {tok.line}"
        )

    def parse_import_file(self) -> ImportFileNode:
        self.expect(TokenType.IMPORT)
        self.expect(TokenType.FILE)
        filepath = self.expect(TokenType.STRING_LITERAL).value
        self.expect(TokenType.INTO)
        table_name = self.expect(TokenType.IDENTIFIER).value
        return ImportFileNode(table_name, filepath)

    def parse_delete(self) -> DeleteNode:
        self.expect(TokenType.DELETE)
        self.expect(TokenType.FROM)
        table_name = self.expect(TokenType.IDENTIFIER).value
        self.expect(TokenType.WHERE)
        col = self.expect(TokenType.IDENTIFIER).value
        self.expect(TokenType.EQUAL)
        value = self.read_literal()
        return DeleteNode(table_name, col, value)

    def read_limit(self) -> int:
        """Lee la clausula obligatoria LIMIT k de las consultas de recuperacion."""
        self.expect(TokenType.LIMIT)
        return self.expect(TokenType.INTEGER_LITERAL).value

    def read_retrieval_method(self):
        """Lee la clausula opcional USING <metodo> para forzar el motor en experimentos.

        Texto:      USING SEQUENTIAL | USING INVERTED
        Multimedia: USING SEQUENTIAL | USING MULTIMEDIA
        """
        if self.peek().type != TokenType.USING:
            return None
        self.advance()
        tok = self.peek()
        if tok.type == TokenType.SEQUENTIAL:
            self.advance()
            return "sequential"
        if tok.type == TokenType.INVERTED:
            self.advance()
            return "inverted"
        if tok.type == TokenType.MULTIMEDIA:
            self.advance()
            return "multimedia"
        raise SyntacticError(
            f"USING en una consulta solo permite SEQUENTIAL, INVERTED o MULTIMEDIA; "
            f"se obtuvo '{tok.value}' en línea {tok.line}"
        )

    def read_literal(self):
        tok = self.peek()
        if tok.type in (TokenType.INTEGER_LITERAL, TokenType.FLOAT_LITERAL, TokenType.STRING_LITERAL):
            return self.advance().value
        if tok.type == TokenType.TRUE_LITERAL:
            self.advance()
            return True
        if tok.type == TokenType.FALSE_LITERAL:
            self.advance()
            return False
        if tok.type == TokenType.DATE:
            self.advance()
            return DateLiteralNode(self.expect(TokenType.STRING_LITERAL).value)
        if tok.type == TokenType.TIME:
            self.advance()
            return TimeLiteralNode(self.expect(TokenType.STRING_LITERAL).value)
        raise SyntacticError(
            f"Se esperaba un valor literal, se obtuvo '{tok.value}' "
            f"({tok.type.name}) en línea {tok.line}"
        )

    def read_column_type(self) -> str:
        tok = self.peek()
        if tok.type == TokenType.INT_TYPE:
            self.advance()
            return "INT"
        if tok.type == TokenType.INTEGER_TYPE:
            self.advance()
            return "INTEGER"
        if tok.type == TokenType.SMALLINT:
            self.advance()
            return "SMALLINT"
        if tok.type == TokenType.BIGINT:
            self.advance()
            return "BIGINT"
        if tok.type == TokenType.REAL:
            self.advance()
            return "REAL"
        if tok.type == TokenType.DOUBLE:
            self.advance()
            self.expect(TokenType.PRECISION)
            return "DOUBLE PRECISION"
        if tok.type == TokenType.BOOLEAN:
            self.advance()
            return "BOOLEAN"
        if tok.type == TokenType.CHAR:
            self.advance()
            self.expect(TokenType.LEFT_PARENTHESIS)
            size = self.expect(TokenType.INTEGER_LITERAL).value
            self.expect(TokenType.RIGHT_PARENTHESIS)
            return f"CHAR({size})"
        if tok.type == TokenType.DATE:
            self.advance()
            return "DATE"
        if tok.type == TokenType.TIME:
            self.advance()
            return "TIME"
        if tok.type == TokenType.TEXT_TYPE:
            self.advance()
            return "TEXT"
        if tok.type == TokenType.IMAGE_TYPE:
            self.advance()
            return "IMAGE"
        if tok.type == TokenType.AUDIO_TYPE:
            self.advance()
            return "AUDIO"
        raise SyntacticError(
            f"Se esperaba un tipo de dato, se obtuvo '{tok.value}' "
            f"({tok.type.name}) en línea {tok.line}"
        )

    def read_index_type(self) -> str:
        tok = self.peek()
        if tok.type == TokenType.RTREE:
            self.advance()
            return "rtree"
        if tok.type == TokenType.BPLUS:
            self.advance()
            self.expect(TokenType.TREE)
            return "bplus"
        if tok.type == TokenType.EXTENDIBLE:
            self.advance()
            self.expect(TokenType.HASHING)
            return "hashing"
        if tok.type == TokenType.SEQUENTIAL:
            self.advance()
            self.expect(TokenType.FILE)
            return "sequential"
        if tok.type == TokenType.INVERTED:
            self.advance()
            return "inverted"
        if tok.type == TokenType.MULTIMEDIA:
            self.advance()
            return "multimedia"
        raise SyntacticError(
            f"Se esperaba una técnica de índice válida, se obtuvo '{tok.value}' "
            f"({tok.type.name}) en línea {tok.line}"
        )

    def read_primary_index_type(self) -> str:
        tok = self.peek()
        if tok.type == TokenType.BPLUS:
            self.advance()
            self.expect(TokenType.TREE)
            return "bplus"
        if tok.type == TokenType.EXTENDIBLE:
            self.advance()
            self.expect(TokenType.HASHING)
            return "hashing"
        if tok.type == TokenType.SEQUENTIAL:
            self.advance()
            self.expect(TokenType.FILE)
            return "sequential"
        raise SyntacticError(
            "PRIMARY KEY USING solo permite BPLUS TREE, EXTENDIBLE HASHING o "
            f"SEQUENTIAL FILE; se obtuvo '{tok.value}' ({tok.type.name}) en lÃ­nea {tok.line}"
        )

    def expect(self, token_type: TokenType) -> Token:
        tok = self.peek()
        if tok.type != token_type:
            raise SyntacticError(
                f"Se esperaba {token_type.name}, "
                f"se obtuvo '{tok.value}' ({tok.type.name}) en línea {tok.line}"
            )
        return self.advance()

    def peek(self) -> Token:
        return self.tokens[self.pos]

    def advance(self) -> Token:
        tok = self.tokens[self.pos]
        if tok.type != TokenType.EOF:
            self.pos += 1
        return tok
