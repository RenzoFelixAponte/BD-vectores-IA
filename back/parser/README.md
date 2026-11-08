# Parser

Este modulo reune el estado actual del parser del proyecto. Su responsabilidad es transformar una consulta SQL del subconjunto definido por el equipo en tokens validos y luego en nodos AST consumibles por el resto del sistema.

Pruebas manuales del lexer y parser:

```powershell
python -m back.parser.__init__
```

## Analisis Lexico

El analisis lexico esta implementado en `lexical_analyzer.py`. Su trabajo es recorrer la consulta caracter por caracter, validar que cada simbolo pertenezca al alfabeto aceptado por el proyecto y generar la secuencia de tokens que utilizara el parser.

Actualmente el lexer reconoce:

- Sentencias `CREATE TABLE`, `CREATE INDEX`, `SELECT`, `INSERT` y `DELETE`
- Identificadores de tablas y columnas con la forma `[A-Za-z_][A-Za-z0-9_]*`
- Literales enteros, flotantes, cadenas entre comillas simples y booleanos
- Literales tipados para `DATE` y `TIME` en la forma `DATE 'yyyy-mm-dd'` y `TIME 'hh:mm:ss'`
- Delimitadores `(`, `)`, `,`, `;` y `*`
- Operadores `=`, `<`, `>`, `<=`, `>=`, `BETWEEN`, `AND`, `IN`
- Palabras clave `PRIMARY KEY` y `USING` para la declaracion obligatoria de la llave primaria y su tecnica de indice opcional
- Tecnicas de indice expresadas como combinaciones de keywords: `RTREE`, `BPLUS TREE`, `EXTENDIBLE HASHING` y `SEQUENTIAL FILE`

El lexer tambien soporta los tipos de datos de longitud fija acordados para el proyecto. Esta restriccion se mantiene porque la capa de almacenamiento trabaja con registros de tamano fijo.

| Tipo de dato | Descripcion | Tamano fijo |
| --- | --- | --- |
| `INTEGER` / `INT` | Entero de proposito general | 4 bytes |
| `SMALLINT` | Entero pequeno | 2 bytes |
| `BIGINT` | Entero grande | 8 bytes |
| `REAL` | Numero de punto flotante | 4 bytes |
| `DOUBLE PRECISION` | Numero de punto flotante doble | 8 bytes |
| `BOOLEAN` | Valor logico verdadero o falso | 1 byte |
| `CHAR(n)` | Cadena de longitud fija | `n` bytes |
| `DATE` | Fecha sin componente de hora | 4 bytes |
| `TIME` | Hora sin componente de fecha | 8 bytes |

Notas actuales del lexer:

- Toda consulta debe terminar con punto y coma, por medio del token `SEMICOLON`
- El path de `FROM FILE` debe escribirse como `STRING_LITERAL`
- El lexer rechaza caracteres inesperados antes de intentar tokenizar

## Analisis Sintactico

El analisis sintactico esta implementado en `parser.py` mediante un parser descendente recursivo. Su entrada es la lista de tokens producida por `LexicalAnalyzer`, y su salida es un nodo del AST definido en `ast_nodes.py`.

En la estructura actual del modulo:

- `parser.py` conserva la API publica `Parser`
- `Parser` es reutilizable: mantiene instancias persistentes del lexer, el parser sintactico y el verificador semantico
- La consulta SQL se entrega en `parse(sql)`
- `LexicalAnalyzer` recibe la consulta en `tokenize(sql)`
- `syntactic_analyzer.py` concentra las reglas del analisis sintactico
- `SyntacticAnalyzer` recibe la lista de tokens en `parse(tokens)` y encapsula su excepcion interna
- `parser.py` traduce los errores sintacticos internos a `ParseError` para conservar la API publica estable
- `semantic_analyzer.py` ejecuta la validacion semantica posterior sobre el AST

Gramatica actual del subconjunto:

```ebnf
query ::= create_table_stmt
        | create_index_stmt
        | drop_table_stmt
        | drop_index_stmt
        | insert_stmt
        | select_stmt
        | delete_stmt

create_table_stmt ::= CREATE TABLE identifier LEFT_PARENTHESIS column_def (COMMA column_def)* RIGHT_PARENTHESIS from_file_clause SEMICOLON

column_def ::= identifier data_type primary_key_clause

primary_key_clause ::= PRIMARY KEY primary_index_clause
                     | epsilon

primary_index_clause ::= USING primary_index_type
                       | epsilon

primary_index_type ::= BPLUS TREE
                     | EXTENDIBLE HASHING
                     | SEQUENTIAL FILE

from_file_clause ::= FROM FILE string_literal
                   | epsilon

create_index_stmt ::= CREATE INDEX identifier ON identifier LEFT_PARENTHESIS index_column_list RIGHT_PARENTHESIS USING index_type SEMICOLON

drop_table_stmt ::= DROP TABLE identifier SEMICOLON

drop_index_stmt ::= DROP INDEX identifier ON identifier SEMICOLON

index_column_list ::= identifier
                    | identifier COMMA identifier

index_type ::= BPLUS TREE
             | EXTENDIBLE HASHING
             | SEQUENTIAL FILE
             | RTREE

insert_stmt ::= INSERT INTO identifier VALUES LEFT_PARENTHESIS literal (COMMA literal)* RIGHT_PARENTHESIS SEMICOLON

select_stmt ::= SELECT ASTERISK FROM identifier select_tail

select_tail ::= SEMICOLON
              | WHERE identifier select_predicate SEMICOLON

select_predicate ::= EQUAL literal
                   | comparison_operator literal
                   | BETWEEN literal AND literal
                   | IN LEFT_PARENTHESIS POINT LEFT_PARENTHESIS literal COMMA literal RIGHT_PARENTHESIS COMMA spatial_predicate RIGHT_PARENTHESIS

comparison_operator ::= LESS_THAN
                      | GREATER_THAN
                      | LESS_THAN_OR_EQUAL
                      | GREATER_THAN_OR_EQUAL

spatial_predicate ::= RADIUS literal
                    | K integer_literal

delete_stmt ::= DELETE FROM identifier WHERE identifier EQUAL literal SEMICOLON

data_type ::= INT_TYPE
            | INTEGER_TYPE
            | SMALLINT
            | BIGINT
            | REAL
            | DOUBLE PRECISION
            | BOOLEAN
            | CHAR LEFT_PARENTHESIS integer_literal RIGHT_PARENTHESIS
            | DATE
            | TIME

literal ::= integer_literal
          | float_literal
          | string_literal
          | TRUE_LITERAL
          | FALSE_LITERAL
          | DATE string_literal
          | TIME string_literal
```

Sentencias soportadas en el estado actual:

1. `CREATE TABLE <name> (<column> <type> [PRIMARY KEY [USING <primary_index_technique>]], ...) [FROM FILE <path>];`
2. `CREATE INDEX <index_name> ON <table> (<column>) USING <single_column_technique>;`
3. `CREATE INDEX <index_name> ON <table> (<column_1>, <column_2>) USING RTREE;`
4. `DROP TABLE <table>;`
5. `DROP INDEX <index_name> ON <table>;`
6. `SELECT * FROM <table> WHERE <column> = <value>;`
7. `SELECT * FROM <table> WHERE <column> <comparison_operator> <value>;`
8. `SELECT * FROM <table> WHERE <column> BETWEEN <value_1> AND <value_2>;`
9. `SELECT * FROM <table> WHERE <column> IN (POINT(<x>, <y>), RADIUS <r>);`
10. `SELECT * FROM <table> WHERE <column> IN (POINT(<x>, <y>), K <k>);`
11. `INSERT INTO <table> VALUES (...);`
12. `DELETE FROM <table> WHERE <column> = <value>;`

Reglas sintacticas ya consolidadas:

- Cada entrada del parser contiene una sola consulta
- El punto y coma final es obligatorio
- `CREATE TABLE` acepta `FROM FILE` solo con una cadena entre comillas simples
- `CREATE TABLE` ya no declara indices; solo esquema y `PRIMARY KEY`
- `PRIMARY KEY USING` solo permite `BPLUS TREE`, `EXTENDIBLE HASHING` o `SEQUENTIAL FILE`
- `CREATE INDEX` exige nombre explicito del indice y separa los indices escalares de `RTREE`
- `DROP INDEX` exige nombre explicito del indice y nombre de tabla
- `DELETE` solo acepta comparacion por igualdad
- `SELECT` acepta `=`, `<`, `>`, `<=`, `>=`, `BETWEEN` y las dos variantes espaciales con `POINT`
- La llave primaria puede usarse tanto para busquedas exactas como para busquedas por rango

Nodos AST actualmente definidos:

- `CreateTableNode`
- `CreateIndexNode`
- `DropTableNode`
- `DropIndexNode`
- `InsertNode`
- `SelectAllNode`
- `SelectEqualNode`
- `SelectComparisonNode`
- `SelectRangeNode`
- `SelectPointRadiusNode`
- `SelectKNNNode`
- `DeleteNode`

## Verificacion Semantica

La verificacion semantica consulta el catalogo persistido del proyecto antes de que el nodo llegue al engine. La fuente de verdad actual es:

- `back/data/catalog/pg_class.json`
- `back/data/catalog/pg_attribute.json`
- `back/data/catalog/pg_index.json`
- `back/data/catalog/pg_constraint.json`

Restricciones semanticas implementadas actualmente:

- Verificar que no existan nombres de columna repetidos dentro de una misma tabla en `CREATE TABLE`
- Verificar que `CREATE TABLE` declare exactamente una columna `PRIMARY KEY`
- Verificar que `PRIMARY KEY USING` solo use una tecnica de indice primaria permitida
- Verificar que no se intente crear una tabla con un nombre ya existente en el catalogo
- Verificar que `CHAR(n)` use un tamano entero positivo mayor que cero
- Verificar que `CREATE INDEX` apunte a una tabla existente
- Verificar que las columnas referenciadas por `CREATE INDEX`, `SELECT`, `DELETE` e `INSERT` existan realmente en el esquema de la tabla
- Verificar que no exista ya un indice secundario con el mismo nombre en la misma tabla
- Verificar que `CREATE INDEX USING RTREE` declare exactamente dos columnas distintas
- Verificar que `CREATE INDEX` escalar declare exactamente una columna
- Verificar que `DROP TABLE` apunte a una tabla existente
- Verificar que `DROP INDEX` apunte a una tabla existente y a un indice secundario realmente definido en ella
- Verificar que `INSERT` reciba la cantidad exacta de valores que la tabla espera
- Verificar compatibilidad basica entre literales del parser y tipos declarados de columna
- Verificar que `BETWEEN` reciba dos literales comparables entre si
- Verificar que `K` reciba un entero positivo en busquedas `IN (POINT(...), K ...)`
- Verificar que `RADIUS` reciba un valor numerico positivo
- Verificar que `POINT(x, y)` reciba coordenadas numericas
- Verificar que una consulta espacial solo se ejecute sobre una tabla que tenga al menos un indice `RTREE`
- Verificar que una declaracion `FROM FILE` use un `STRING_LITERAL` no vacio
- Verificar formato semantico de literales `DATE 'yyyy-mm-dd'` y `TIME 'hh:mm:ss'`

Restricciones que siguen fuera del verificador y permanecen en el engine o en los indices:

- Deteccion de clave primaria duplicada al insertar
- Logica fisica de actualizacion de indices primarios y secundarios
- Ejecucion de scans secuenciales, scans por indice y consultas espaciales
- Metricas de I/O y tiempo
- Errores internos de lectura y escritura sobre archivos e indices

En consecuencia, el estado actual del modulo debe interpretarse asi:

- El analisis lexico esta operativo
- El analisis sintactico esta operativo dentro del subconjunto definido
- La verificacion semantica ya depende del catalogo real de la base
- El engine sigue siendo responsable de la ejecucion fisica
