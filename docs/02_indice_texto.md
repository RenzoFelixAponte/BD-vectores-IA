# 2. Backend – Índice Invertido para Texto

> Rúbrica: construcción del índice invertido en memoria secundaria; ejecución
> eficiente de consultas con similitud de coseno; explicación del mecanismo de
> índices invertidos en PostgreSQL.

Código: `back/retrieval/text/`

## 2.1 Construcción del índice en memoria secundaria (SPIMI)
<!-- TODO: describir el método SPIMI (bloques en RAM → volcado ordenado a disco →
merge k-vías). Archivos: tokenizer.py, spimi.py, inverted_index.py. -->

## 2.2 Modelo de pesos TF-IDF
<!-- TODO: cálculo de TF, IDF y normas de documento; estructura de postings y
diccionario en disco. -->

## 2.3 Consultas por similitud de coseno
<!-- TODO: ranking term-at-a-time con acumulador + heap top-k; coseno normalizado.
Archivos: cosine_ranker.py, text_retriever.py. Operador SQL: `@@`. -->

## 2.4 Índices invertidos en PostgreSQL (GIN)
<!-- TODO: explicar cómo PostgreSQL construye GIN/tsvector/tsquery y cómo se
compara con la implementación propia. -->
