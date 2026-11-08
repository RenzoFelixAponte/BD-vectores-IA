"""Ranking por similitud de coseno TF-IDF sobre el indice invertido (a mano).

Algoritmo term-at-a-time:
  1. Vector TF-IDF disperso de la consulta.
  2. Por cada termino de la consulta, leer sus postings y acumular el producto
     punto en un acumulador {doc_id: score}.
  3. Normalizar por (norma_consulta * norma_documento) -> coseno.
  4. Top-k con heap (sin ordenar toda la coleccion).

Chunking: cuando el indice se construyo por fragmentos, el "doc_id" de los postings
es en realidad un chunk_id. Antes del top-k se re-agrega cada chunk a su documento
padre (via index.chunk_map) quedandose con el MEJOR chunk (score maximo). Asi los
callers siguen recibiendo (clave_primaria, score) sin cambios.
"""

from __future__ import annotations

import heapq
import math
from collections import defaultdict

from .chunker import Chunker
from .inverted_index import InvertedIndex


class CosineRanker:
    def __init__(self, index: InvertedIndex, chunker: Chunker | None = None):
        self.index = index
        # chunk_map: {chunk_id: clave_primaria_padre} o None si el indice no usa chunking.
        self.chunk_map = getattr(index, "chunk_map", None)
        # chunker: solo se necesita en modo secuencial, para partir cada documento con
        # las MISMAS fronteras usadas al construir el indice.
        self.chunker = chunker

    def _aggregate_to_parents(self, chunk_scores) -> list[tuple[int, float]]:
        """Colapsa [(chunk_id, score)] a [(parent_id, mejor_score)] usando chunk_map."""
        best: dict[int, float] = {}
        for chunk_id, score in chunk_scores:
            parent = self.chunk_map.get(chunk_id, chunk_id)
            if score > best.get(parent, float("-inf")):
                best[parent] = score
        return list(best.items())

    def query_vector(self, query_terms: list[str]) -> tuple[dict[str, float], float]:
        """Vector TF-IDF disperso de la consulta y su norma."""
        tf: dict[str, int] = defaultdict(int)
        for t in query_terms:
            tf[t] += 1
        vector: dict[str, float] = {}
        for term, freq in tf.items():
            idf = self.index.get_idf(term)
            if idf > 0:
                vector[term] = (1.0 + math.log(freq)) * idf
        norm = math.sqrt(sum(w * w for w in vector.values()))
        return vector, norm

    def rank(self, query_terms: list[str], k: int) -> list[tuple[int, float]]:
        """Top-k documentos por coseno usando el indice invertido."""
        if k <= 0:
            raise ValueError("k debe ser positivo")
        query, query_norm = self.query_vector(query_terms)
        if not query or query_norm == 0.0:
            return []

        scores: dict[int, float] = defaultdict(float)
        for term, q_weight in query.items():
            idf = self.index.get_idf(term)
            for doc_id, tf in self.index.get_postings(term):
                doc_weight = (1.0 + math.log(tf)) * idf
                scores[doc_id] += q_weight * doc_weight

        # Coseno por documento/chunk (doc_id aqui puede ser un chunk_id).
        ranked: list[tuple[int, float]] = []
        for doc_id, dot in scores.items():
            denom = query_norm * self.index.get_document_norm(doc_id)
            ranked.append((doc_id, dot / denom if denom > 0 else 0.0))

        # Si el indice esta fragmentado, re-agrega cada chunk a su documento padre.
        if self.chunk_map is not None:
            ranked = self._aggregate_to_parents(ranked)
        return heapq.nlargest(k, ranked, key=lambda item: (item[1], -item[0]))

    def _chunk_cosine(self, query: dict[str, float], query_norm: float, terms: list[str]) -> float:
        """Coseno de un unico fragmento (calcula su norma TF-IDF al vuelo)."""
        tf: dict[str, int] = defaultdict(int)
        for t in terms:
            tf[t] += 1
        dot = 0.0
        norm_sq = 0.0
        for term, freq in tf.items():
            idf = self.index.get_idf(term)
            if idf <= 0:
                continue
            weight = (1.0 + math.log(freq)) * idf
            norm_sq += weight * weight
            if term in query:
                dot += query[term] * weight
        doc_norm = math.sqrt(norm_sq)
        return dot / (query_norm * doc_norm) if doc_norm > 0 else 0.0

    def rank_sequential(self, query_terms: list[str], k: int, documents) -> list[tuple[int, float]]:
        """Variante SECUENCIAL (sin indice): recorre todos los documentos y calcula
        coseno uno por uno. Baseline para la experimentacion (USING SEQUENTIAL).

        documents: iterable de (doc_id, terms:list[str]).

        Si hay un chunker configurado, cada documento se parte en fragmentos y se le
        asigna el score de su MEJOR fragmento, para ser consistente con el indice
        invertido fragmentado (misma definicion de score = mejor chunk).
        """
        if k <= 0:
            raise ValueError("k debe ser positivo")
        query, query_norm = self.query_vector(query_terms)
        if not query or query_norm == 0.0:
            return []

        ranked: list[tuple[int, float]] = []
        for doc_id, terms in documents:
            if self.chunker is not None:
                chunks = self.chunker.chunk_terms(terms)
                score = max((self._chunk_cosine(query, query_norm, c) for c in chunks), default=0.0)
            else:
                score = self._chunk_cosine(query, query_norm, terms)
            ranked.append((doc_id, score))
        return heapq.nlargest(k, ranked, key=lambda item: (item[1], -item[0]))
