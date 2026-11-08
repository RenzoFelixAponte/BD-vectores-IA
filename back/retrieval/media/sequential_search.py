"""KNN SECUENCIAL sobre histogramas (baseline, fuerza bruta).

Recorre todos los histogramas de la coleccion, calcula la similitud con el
histograma consulta y mantiene los k mejores con un heap. Es el baseline contra
el cual se compara el KNN indexado (rubrica: 'secuencial e indexada').
Costo O(N) por consulta.
"""

from __future__ import annotations

import heapq

import numpy as np

from ..similarity import cosine_similarity_dense, euclidean_distance


class SequentialSearch:
    def __init__(self, histograms: dict[int, np.ndarray] | None = None, metric: str = "cosine"):
        """histograms: {doc_id: histograma denso}. metric: 'cosine' | 'euclidean'."""
        self.histograms: dict[int, np.ndarray] = histograms or {}
        self.metric = metric

    def add(self, doc_id: int, histogram) -> None:
        self.histograms[doc_id] = np.asarray(histogram, dtype=np.float32)

    def knn(self, query_histogram, k: int) -> list[tuple[int, float]]:
        """Top-k vecinos por fuerza bruta.

        Salida: [(doc_id, score)] orden desc por score (mejor primero).
        Para coseno score = similitud; para euclidiana score = -distancia.
        """
        if k <= 0:
            raise ValueError("k debe ser positivo")
        scored: list[tuple[int, float]] = []
        for doc_id, hist in self.histograms.items():
            if self.metric == "euclidean":
                score = -euclidean_distance(query_histogram, hist)
            else:
                score = cosine_similarity_dense(query_histogram, hist)
            scored.append((doc_id, score))
        return heapq.nlargest(k, scored, key=lambda item: (item[1], -item[0]))
