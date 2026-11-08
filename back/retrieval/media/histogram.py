"""Histograma Bag of Visual/Acoustic Words, a mano.

Convierte la lista de word_id (salida de Vocabulary.quantize) en un histograma de
tamano k. Es el 'vector documento' que indexan y comparan los motores KNN.
Pipeline tipico: build_histogram (TF normalizada) -> apply_tfidf (pondera por IDF
global) -> to_sparse (para el indice invertido de codewords).
"""

from __future__ import annotations

import math

import numpy as np


def build_histogram(word_ids: list[int], k: int, normalize: bool = True) -> np.ndarray:
    """Histograma de frecuencias de un item: cuantas veces aparece cada palabra.

    Entrada: word_ids (palabras del item), k (tamano del codebook).
    Salida:  vector denso de longitud k (float32). Si normalize, divide por el
             total (term frequency) para que items con distinto numero de
             descriptores sean comparables.
    """
    hist = np.zeros(k, dtype=np.float64)
    for w in word_ids:
        if 0 <= w < k:
            hist[w] += 1.0
    if normalize:
        total = hist.sum()
        if total > 0:
            hist /= total
    return hist.astype(np.float32)


def compute_idf(histograms, k: int) -> np.ndarray:
    """IDF por palabra sobre toda la coleccion: log(N / df) suavizado.

    Entrada: histograms iterable de vectores densos (k,); k.
    Salida:  vector idf de longitud k.
    """
    df = np.zeros(k, dtype=np.float64)
    n_docs = 0
    for hist in histograms:
        n_docs += 1
        df += (np.asarray(hist) > 0).astype(np.float64)
    idf = np.log((1.0 + n_docs) / (1.0 + df)) + 1.0
    return idf.astype(np.float32)


def apply_tfidf(histogram, idf) -> np.ndarray:
    """Pondera el histograma TF por IDF y normaliza L2 (para coseno)."""
    weighted = np.asarray(histogram, dtype=np.float64) * np.asarray(idf, dtype=np.float64)
    norm = math.sqrt(float(weighted @ weighted))
    if norm > 0:
        weighted /= norm
    return weighted.astype(np.float32)


def to_sparse(histogram) -> dict[int, float]:
    """Convierte un histograma denso a {word_id: peso} para el indice invertido."""
    arr = np.asarray(histogram)
    return {int(i): float(arr[i]) for i in np.flatnonzero(arr)}
