"""Experimentacion del Proyecto 2.

Compara los motores de recuperacion segun la rubrica: rendimiento, precision y
escalabilidad. Genera las tablas y graficos del informe.

  datasets           -> prepara colecciones de prueba (texto y multimedia) a varias escalas
  run_text_benchmark -> indice invertido (coseno) vs scan secuencial vs PostgreSQL (GIN)
  run_media_benchmark-> KNN indexado vs KNN secuencial; impacto de k y de la dimension
  plots              -> graficos comparativos para el informe
"""
