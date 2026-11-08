"""KNN INDEXADO sobre histogramas mediante indice invertido de codewords.

Idea (analoga al indice invertido de texto): cada 'palabra visual/acustica' apunta
a los documentos cuyo histograma la contiene. En la consulta solo se evaluan los
documentos que comparten al menos una palabra con la consulta (candidatos), en vez
de toda la coleccion. Reduce el costo frente al KNN secuencial y aprovecha que los
histogramas TF-IDF son dispersos.
"""

from __future__ import annotations

import heapq
import json
from collections import defaultdict
from pathlib import Path

from ..similarity import dot_sparse, l2_norm


class HistogramIndex:
    def __init__(self, index_dir: str | None = None):
        self.index_dir = index_dir
        self.postings: dict[int, list[tuple[int, float]]] = {}  # word_id -> [(doc_id, peso)]
        self.norms: dict[int, float] = {}                        # doc_id -> norma L2
        self._docs: dict[int, dict[int, float]] = {}             # doc_id -> histograma disperso

    def build(self, sparse_histograms) -> "HistogramIndex":
        """Construye el indice invertido de codewords.

        Entrada: iterable de (doc_id, {word_id: peso}).
        """
        postings: dict[int, list[tuple[int, float]]] = defaultdict(list)
        for doc_id, sparse in sparse_histograms:
            self.norms[doc_id] = l2_norm(sparse)
            self._docs[doc_id] = dict(sparse)
            for word_id, weight in sparse.items():
                postings[word_id].append((doc_id, weight))
        self.postings = dict(postings)
        return self

    def knn(self, query_sparse: dict[int, float], k: int) -> list[tuple[int, float]]:
        """Top-k usando solo documentos candidatos (los que comparten codewords).

        Acumula el producto punto por documento recorriendo los postings de las
        palabras activas de la consulta; normaliza por las normas -> coseno.
        """
        if k <= 0:
            raise ValueError("k debe ser positivo")
        dots: dict[int, float] = defaultdict(float)
        for word_id, q_weight in query_sparse.items():
            for doc_id, d_weight in self.postings.get(word_id, []):
                dots[doc_id] += q_weight * d_weight

        query_norm = l2_norm(query_sparse)
        scored: list[tuple[int, float]] = []
        for doc_id, dot in dots.items():
            denom = query_norm * self.norms.get(doc_id, 0.0)
            scored.append((doc_id, dot / denom if denom > 0 else 0.0))
        return heapq.nlargest(k, scored, key=lambda item: (item[1], -item[0]))

    # ------------------------------------------------------------------
    # Persistencia (postings + normas a disco)
    # ------------------------------------------------------------------
    def save(self, path: str | Path) -> None:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "postings": {str(w): p for w, p in self.postings.items()},
            "norms": {str(d): n for d, n in self.norms.items()},
        }
        out.write_text(json.dumps(payload), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "HistogramIndex":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        index = cls()
        index.postings = {
            int(w): [(int(d), float(weight)) for d, weight in plist]
            for w, plist in payload["postings"].items()
        }
        index.norms = {int(d): float(n) for d, n in payload["norms"].items()}
        docs: dict[int, dict[int, float]] = defaultdict(dict)
        for word_id, postings in index.postings.items():
            for doc_id, weight in postings:
                docs[doc_id][word_id] = weight
        index._docs = {doc_id: dict(sparse) for doc_id, sparse in docs.items()}
        return index

    def index_size_bytes(self) -> int:
        return sum(len(p) for p in self.postings.values())
