from .lexical_analyzer import LexicalAnalyzer
from .syntactic_analyzer import SyntacticAnalyzer, SyntacticError
from .semantic_analyzer import SemanticAnalyzer, SemanticError

class ParseError(Exception):
    pass

class Parser:
    """
    Fachada pública del parser del proyecto.
    """

    # ------------------------------------------------------------------------------
    # API publica del parser: Inicializa las 3 fases del parser.
    # ------------------------------------------------------------------------------
    def __init__(self, db=None):
        self.lexical_analyzer   = LexicalAnalyzer()
        self.syntactic_analyzer = SyntacticAnalyzer()
        self.semantic_analyzer  = SemanticAnalyzer(db=db)

    # ------------------------------------------------------------------------------
    # API publica del parser: Recibe la consulta y la analiza.
    # ------------------------------------------------------------------------------
    def parse(self, sql: str):
        # Fase 1: Análisis léxico
        tokens = self.lexical_analyzer.tokenize(sql)
        
        # Fase 2: Análisis sintáctico
        try:
            node = self.syntactic_analyzer.parse(tokens)
        except SyntacticError as error:
            raise ParseError(str(error)) from error
        
        # Fase 3: Verificación semántica
        if not self.semantic_analyzer.validate(node):
            raise SemanticError(self.semantic_analyzer.error_message)
        return node
