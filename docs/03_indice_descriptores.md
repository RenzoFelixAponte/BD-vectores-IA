# 3. Backend – Índice Invertido para Descriptores Locales

> Rúbrica: construcción del Bag of Visual/Acoustic Words; diseño de la técnica de
> indexación; búsqueda KNN sobre histogramas (secuencial e indexada); análisis de
> la maldición de la dimensionalidad y estrategias de mitigación.

Código: `back/retrieval/media/`

## 3.1 Descriptores locales
<!-- TODO: SIFT (imagen) y MFCC con ventana deslizante (audio). Archivos:
extractors/image_descriptor.py, extractors/audio_descriptor.py. -->

## 3.2 Bag of Visual / Acoustic Words
<!-- TODO: codebook con K-Means (vocabulary.py) → cuantización → histograma
(histogram.py). Ponderación TF-IDF y normalización. -->

## 3.3 Técnica de indexación
<!-- TODO: índice invertido de codewords (histogram_index.py): cada palabra apunta
a los documentos que la contienen; selección de candidatos. -->

## 3.4 Búsqueda KNN: secuencial vs indexada
<!-- TODO: sequential_search.py (fuerza bruta, baseline) vs histogram_index.py
(indexado). Operador SQL: `<->` con `USING SEQUENTIAL | MULTIMEDIA`. -->

## 3.5 Maldición de la dimensionalidad
<!-- TODO: efecto de la dimensión/tamaño de codebook k; estrategias: histogramas
dispersos, TF-IDF, límite de keypoints, muestreo en el entrenamiento del codebook. -->
