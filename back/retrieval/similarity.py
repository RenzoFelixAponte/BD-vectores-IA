"""Funciones de similitud y distancia implementadas a mano (sin librerias de IR).

Las usan tanto el ranker de texto (coseno sobre vectores TF-IDF dispersos) como
el KNN multimedia (distancia sobre histogramas densos de Bag of Words). Se usa
numpy solo como contenedor numerico; los algoritmos estan escritos a mano.
"""

from __future__ import annotations

import math

import numpy as np


def dot_sparse(a: dict[int, float], b: dict[int, float]) -> float:
    """Producto punto de dos vectores dispersos recorriendo solo la interseccion."""
    # Iterar sobre el vector con menos entradas para que sea O(min(|a|, |b|)).
    if len(a) > len(b):
        a, b = b, a
    total = 0.0
    for term_id, weight in a.items():
        other = b.get(term_id)
        if other is not None:
            total += weight * other
    return total


def l2_norm(vector) -> float:
    """Norma L2 de un vector disperso (dict) o denso (lista / np.ndarray)."""
    if isinstance(vector, dict):
        return math.sqrt(sum(w * w for w in vector.values()))
    arr = np.asarray(vector, dtype=np.float64)
    return float(math.sqrt(float(arr @ arr)))


def cosine_similarity_sparse(
    query: dict[int, float],
    document: dict[int, float],
    query_norm: float | None = None,
    document_norm: float | None = None,
) -> float:
    """Coseno entre dos vectores dispersos {id: peso}.

    Si se pasan las normas precalculadas (las guarda el indice), se evita
    recalcularlas. Devuelve 0 si algun vector es nulo.
    """
    if not query or not document:
        return 0.0
    qn = query_norm if query_norm is not None else l2_norm(query)
    dn = document_norm if document_norm is not None else l2_norm(document)
    if qn == 0.0 or dn == 0.0:
        return 0.0
    return dot_sparse(query, document) / (qn * dn)


def cosine_similarity_dense(a, b) -> float:
    """Coseno entre dos vectores densos (histogramas)."""
    va = np.asarray(a, dtype=np.float64)
    vb = np.asarray(b, dtype=np.float64)
    na = math.sqrt(float(va @ va))
    nb = math.sqrt(float(vb @ vb))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(va @ vb) / (na * nb)


def euclidean_distance(a, b) -> float:
    """Distancia euclidiana entre dos histogramas densos (para KNN)."""
    va = np.asarray(a, dtype=np.float64)
    vb = np.asarray(b, dtype=np.float64)
    diff = va - vb
    return float(math.sqrt(float(diff @ diff)))
