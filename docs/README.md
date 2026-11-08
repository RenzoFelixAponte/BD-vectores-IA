# Informe — Proyecto 2: Recuperación por Contenido (Texto + Multimedia)

Estructura del informe alineada a la rúbrica:

1. [Introducción](01_introduccion.md) — dominio y justificación de la BD multimodal
2. [Índice Invertido para Texto](02_indice_texto.md) — SPIMI, coseno, GIN
3. [Índice Invertido para Descriptores Locales](03_indice_descriptores.md) — BoVW/BoAW, KNN, dimensionalidad
4. [Frontend](04_frontend.md) — parser SQL, GUI, manual, capturas
5. [Experimentación](05_experimentacion.md) — tablas, gráficos y análisis

## Mapa código ↔ informe

| Parte | Código |
| --- | --- |
| Parser SQL (gramática nueva) | `back/parser/` |
| Índice invertido de texto | `back/retrieval/text/` |
| Descriptores locales (BoVW/BoAW + KNN) | `back/retrieval/media/` |
| Similitud/distancias a mano | `back/retrieval/similarity.py` |
| Integración con el motor SQL | `back/engine/executor.py` |
| Experimentos y gráficos | `back/experiments/` |
| GUI | `frontend/` |
