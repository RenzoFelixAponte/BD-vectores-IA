from enum import Enum, auto


class TokenType(Enum):
    # Palabras clave
    CREATE = auto(); TABLE = auto(); FROM = auto(); FILE = auto()
    IMPORT = auto()
    DROP = auto()
    SELECT = auto(); WHERE = auto(); COUNT = auto()
    INSERT = auto(); INTO = auto(); VALUES = auto()
    DELETE = auto(); INDEX = auto()
    POINT = auto(); RADIUS = auto(); K = auto()
    ON = auto(); USING = auto()
    PRIMARY = auto(); KEY = auto()
    # Tipos de índices
    SEQUENTIAL = auto(); EXTENDIBLE = auto(); HASHING = auto()
    BPLUS = auto(); TREE = auto(); RTREE = auto()
    # Tipos de datos
    INT_TYPE = auto(); INTEGER_TYPE = auto(); SMALLINT = auto()
    BIGINT = auto(); REAL = auto(); DOUBLE = auto()
    PRECISION = auto(); BOOLEAN = auto(); CHAR = auto()
    DATE = auto(); TIME = auto()
    # Tipos de datos de contenido (Proyecto 2: recuperacion por contenido)
    TEXT_TYPE = auto(); IMAGE_TYPE = auto(); AUDIO_TYPE = auto()
    # Indices de recuperacion por contenido
    INVERTED = auto(); MULTIMEDIA = auto()
    # Recuperacion: top-k y operadores de similitud
    LIMIT = auto()
    MATCH = auto()   # @@  -> busqueda textual rankeada por coseno
    SIM = auto()     # <-> -> similitud / KNN multimedia por ejemplo
    # Literales
    IDENTIFIER = auto()
    INTEGER_LITERAL = auto()
    FLOAT_LITERAL = auto()
    STRING_LITERAL = auto()
    TRUE_LITERAL = auto(); FALSE_LITERAL = auto()
    # Símbolos
    LEFT_PARENTHESIS = auto(); RIGHT_PARENTHESIS = auto()
    COMMA = auto(); SEMICOLON = auto()
    ASTERISK = auto()
    # Operadores
    LESS_THAN_OR_EQUAL = auto(); GREATER_THAN_OR_EQUAL = auto()
    LESS_THAN = auto(); GREATER_THAN = auto()
    EQUAL = auto(); BETWEEN = auto()
    AND = auto(); IN = auto()
    # Control
    EOF = auto()


class Token:
    def __init__(self, type: TokenType, value, line: int):
        self.type = type
        self.value = value
        self.line = line

    def __repr__(self):
        return f"Token({self.type.name}, {self.value!r}, line={self.line})"


_KEYWORDS: dict[str, TokenType] = {
    "CREATE": TokenType.CREATE, "TABLE": TokenType.TABLE,
    "DROP": TokenType.DROP,
    "IMPORT": TokenType.IMPORT,
    "FROM": TokenType.FROM, "FILE": TokenType.FILE,
    "SELECT": TokenType.SELECT, "WHERE": TokenType.WHERE, "COUNT": TokenType.COUNT,
    "BETWEEN": TokenType.BETWEEN, "AND": TokenType.AND,
    "INSERT": TokenType.INSERT, "INTO": TokenType.INTO,
    "VALUES": TokenType.VALUES, "DELETE": TokenType.DELETE,
    "INDEX": TokenType.INDEX, "POINT": TokenType.POINT,
    "RADIUS": TokenType.RADIUS, "IN": TokenType.IN,
    "K": TokenType.K,
    "ON": TokenType.ON, "USING": TokenType.USING,
    "PRIMARY": TokenType.PRIMARY, "KEY": TokenType.KEY,
    "SEQUENTIAL": TokenType.SEQUENTIAL, "EXTENDIBLE": TokenType.EXTENDIBLE,
    "HASHING": TokenType.HASHING, "BPLUS": TokenType.BPLUS,
    "TREE": TokenType.TREE, "RTREE": TokenType.RTREE,
    "INT": TokenType.INT_TYPE, "INTEGER": TokenType.INTEGER_TYPE,
    "SMALLINT": TokenType.SMALLINT, "BIGINT": TokenType.BIGINT,
    "REAL": TokenType.REAL, "DOUBLE": TokenType.DOUBLE,
    "PRECISION": TokenType.PRECISION, "BOOLEAN": TokenType.BOOLEAN,
    "CHAR": TokenType.CHAR, "DATE": TokenType.DATE,
    "TIME": TokenType.TIME,
    "TEXT": TokenType.TEXT_TYPE, "IMAGE": TokenType.IMAGE_TYPE,
    "AUDIO": TokenType.AUDIO_TYPE,
    "INVERTED": TokenType.INVERTED, "MULTIMEDIA": TokenType.MULTIMEDIA,
    "LIMIT": TokenType.LIMIT,
    "TRUE": TokenType.TRUE_LITERAL, "FALSE": TokenType.FALSE_LITERAL,
}

_TWO_CHAR_OPERATORS: dict[str, TokenType] = {
    "<=": TokenType.LESS_THAN_OR_EQUAL,
    ">=": TokenType.GREATER_THAN_OR_EQUAL,
}

_ONE_CHAR_OPERATORS: dict[str, TokenType] = {
    "<": TokenType.LESS_THAN,
    ">": TokenType.GREATER_THAN,
    "=": TokenType.EQUAL,
    "*": TokenType.ASTERISK,
}

_DELIMITERS: dict[str, TokenType] = {
    "(": TokenType.LEFT_PARENTHESIS,
    ")": TokenType.RIGHT_PARENTHESIS,
    ",": TokenType.COMMA,
    ";": TokenType.SEMICOLON,
}


class LexError(Exception):
    pass


class LexicalAnalyzer:
    """
    Tokenizador para el subconjunto SQL del proyecto.
    Input:  sql  cadena con la sentencia SQL
    Output: list[Token] vía tokenize()
    """

    def __init__(self):
        self.sql = ""
        self.pos = 0
        self.line = 1

    def tokenize(self, sql: str) -> list:
        self.sql = sql
        self.pos = 0
        self.line = 1
        tokens = []
        while self.pos < len(self.sql):
            ch = self.sql[self.pos]

            if ch in " \t\r\n":
                self.read_whitespace()
                continue

            # Comentario SQL de línea: -- hasta el fin de línea (se ignora).
            if ch == "-" and self.peek(self.pos + 1) == "-":
                while self.pos < len(self.sql) and self.sql[self.pos] != "\n":
                    self.pos += 1
                continue

            if not self.is_valid_character(ch):
                raise LexError(f"Carácter inesperado '{ch}' en línea {self.line}")

            if ch == "'":
                tokens.append(self.read_string())
                continue

            if self.is_digit(ch) or (
                ch == "-"
                and self.pos + 1 < len(self.sql)
                and self.is_digit(self.sql[self.pos + 1])
            ):
                tokens.append(self.read_number())
                continue

            if self.is_letter(ch) or ch == "_":
                tokens.append(self.read_identifier_or_keyword())
                continue

            if ch in "<>=*@":
                tokens.append(self.read_operator())
                continue

            if ch in "(),;":
                tokens.append(self.read_delimiter())
                continue

            raise LexError(f"Carácter inesperado '{ch}' en línea {self.line}")
        tokens.append(Token(TokenType.EOF, None, self.line))
        return tokens

    def read_string(self) -> Token:
        self.pos += 1
        value = []
        while self.pos < len(self.sql):
            if self.sql[self.pos] == "'":
                if self.peek(self.pos + 1) == "'":
                    value.append("'")
                    self.pos += 2
                    continue
                self.pos += 1
                return Token(TokenType.STRING_LITERAL, "".join(value), self.line)
            value.append(self.sql[self.pos])
            self.pos += 1
        raise LexError(f"Cadena sin cerrar en línea {self.line}")

    def read_number(self) -> Token:
        start = self.pos
        has_decimal_point = False

        if self.sql[self.pos] == "-":
            self.pos += 1

        while self.pos < len(self.sql):
            current = self.sql[self.pos]

            if self.is_digit(current):
                self.pos += 1
                continue

            if current == "." and not has_decimal_point:
                next_char = self.peek(self.pos + 1)
                if next_char is None or not self.is_digit(next_char):
                    break
                has_decimal_point = True
                self.pos += 1
                continue

            break

        if has_decimal_point:
            return Token(TokenType.FLOAT_LITERAL, float(self.sql[start:self.pos]), self.line)
        return Token(TokenType.INTEGER_LITERAL, int(self.sql[start:self.pos]), self.line)

    def read_identifier_or_keyword(self) -> Token:
        start = self.pos
        while self.pos < len(self.sql) and (
            self.sql[self.pos].isalnum() or self.sql[self.pos] == "_"
        ):
            self.pos += 1
        word = self.sql[start:self.pos]
        upper = word.upper()
        if upper in _KEYWORDS:
            return Token(_KEYWORDS[upper], upper, self.line)
        return Token(TokenType.IDENTIFIER, word, self.line)

    def read_operator(self) -> Token:
        ch = self.sql[self.pos]

        # Operador de similitud multimedia: <-> (tres caracteres). Se reconoce
        # antes que '<' o '<=' para no confundirlo con una comparacion.
        if ch == "<" and self.peek(self.pos + 1) == "-" and self.peek(self.pos + 2) == ">":
            self.pos += 3
            return Token(TokenType.SIM, "<->", self.line)

        # Operador de match textual: @@ (dos caracteres).
        if ch == "@":
            if self.peek(self.pos + 1) == "@":
                self.pos += 2
                return Token(TokenType.MATCH, "@@", self.line)
            raise LexError(f"Se esperaba '@@' en línea {self.line}")

        next_char = self.peek(self.pos + 1)

        if next_char is not None:
            candidate = ch + next_char
            if candidate in _TWO_CHAR_OPERATORS:
                self.pos += 2
                return Token(_TWO_CHAR_OPERATORS[candidate], candidate, self.line)

        if ch in _ONE_CHAR_OPERATORS:
            self.pos += 1
            return Token(_ONE_CHAR_OPERATORS[ch], ch, self.line)

        raise LexError(f"Carácter inesperado '{ch}' en línea {self.line}")

    def read_delimiter(self) -> Token:
        ch = self.sql[self.pos]
        if ch in _DELIMITERS:
            self.pos += 1
            return Token(_DELIMITERS[ch], ch, self.line)
        raise LexError(f"Carácter inesperado '{ch}' en línea {self.line}")

    def read_whitespace(self):
        while self.pos < len(self.sql) and self.sql[self.pos] in " \t\r\n":
            if self.sql[self.pos] == "\n":
                self.line += 1
            self.pos += 1

    def is_valid_character(self, ch: str) -> bool:
        return self.is_digit(ch) or self.is_letter(ch) or ch == "_" or self._is_special_character(ch)

    def is_digit(self, ch: str) -> bool:
        return ch.isdigit()

    def is_letter(self, ch: str) -> bool:
        return ch.isalpha()

    def peek(self, position: int):
        if position < 0 or position >= len(self.sql):
            return None
        return self.sql[position]

    def _is_special_character(self, ch: str) -> bool:
        return ch in "(),;=*'-.<>@"
