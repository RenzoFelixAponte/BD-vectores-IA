"""Orquestador de la recuperacion multimedia (punto de entrada del operador <->).

Lo invoca executor._exec_media_search. Une extractor + vocabulary + histogram con
el motor KNN (secuencial o indexado) y devuelve los (doc_id, score) top-k.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .histogram import apply_tfidf, build_histogram, compute_idf, to_sparse
from .histogram_index import HistogramIndex
from .sequential_search import SequentialSearch
from .vocabulary import Vocabulary


class MediaRetriever:
    def __init__(self, vocabulary: Vocabulary, extractor, sequential: SequentialSearch,
                 index: HistogramIndex, idf):
        self.vocabulary = vocabulary
        self.extractor = extractor
        self.sequential = sequential
        self.index = index
        self.idf = np.asarray(idf, dtype=np.float32)

    def _encode(self, path: str):
        """archivo -> descriptores -> visual/acoustic words -> histograma TF-IDF denso."""
        descriptors = self.extractor.extract(path)
        word_ids = self.vocabulary.quantize(descriptors)
        raw = build_histogram(word_ids, self.vocabulary.k)
        return apply_tfidf(raw, self.idf)

    def search(self, query_path: str, k: int, method: str | None = None) -> list[tuple[int, float]]:
        """Top-k (doc_id, score). method: None|'multimedia' (indexado) | 'sequential'."""
        dense = self._encode(query_path)
        if method == "sequential":
            return self.sequential.knn(dense, k)
        return self.index.knn(to_sparse(dense), k)

    @classmethod
    def build(cls, items, index_dir: str, extractor, k: int,
              descriptor_sample: int = 200_000, seed: int = 42) -> "MediaRetriever":
        """Pipeline de construccion (CREATE INDEX ... USING MULTIMEDIA).

        items: iterable de (doc_id:int, ruta_archivo:str).
        Extrae descriptores -> entrena Vocabulary -> histogramas TF-IDF ->
        HistogramIndex + SequentialSearch. Persiste codebook, idf e indice.
        """
        out = Path(index_dir)
        out.mkdir(parents=True, exist_ok=True)

        descriptors_by_doc: dict[int, np.ndarray] = {}
        for doc_id, path in items:
            descriptors_by_doc[doc_id] = extractor.extract(path)

        pool = [d for d in descriptors_by_doc.values() if len(d) > 0]
        if not pool:
            raise ValueError("no se extrajeron descriptores de ningun item")
        all_desc = np.vstack(pool)
        if len(all_desc) > descriptor_sample:
            rng = np.random.default_rng(seed)
            all_desc = all_desc[rng.choice(len(all_desc), size=descriptor_sample, replace=False)]

        vocab = Vocabulary(k=k, seed=seed).fit(all_desc)
        vocab.save(out / "codebook.bin")

        raw = {
            doc_id: build_histogram(vocab.quantize(desc), k)
            for doc_id, desc in descriptors_by_doc.items()
        }
        idf = compute_idf(raw.values(), k)
        dense = {doc_id: apply_tfidf(h, idf) for doc_id, h in raw.items()}
        sparse = {doc_id: to_sparse(h) for doc_id, h in dense.items()}

        index = HistogramIndex(str(out)).build(sparse.items())
        index.save(out / "histogram_index.json")
        np.save(out / "idf.npy", idf)

        sequential = SequentialSearch(dense, metric="cosine")
        return cls(vocab, extractor, sequential, index, idf)

    @classmethod
    def open(cls, index_dir: str, extractor) -> "MediaRetriever":
        """Carga codebook, IDF e indice invertido de histogramas desde disco."""
        base = Path(index_dir)
        vocab = Vocabulary.load(base / "codebook.bin")
        idf = np.load(base / "idf.npy")
        index = HistogramIndex.load(base / "histogram_index.json")
        dense = {
            doc_id: cls._dense_from_sparse(sparse, vocab.k)
            for doc_id, sparse in index._docs.items()
        }
        sequential = SequentialSearch(dense, metric="cosine")
        return cls(vocab, extractor, sequential, index, idf)

    @staticmethod
    def _dense_from_sparse(sparse: dict[int, float], k: int) -> np.ndarray:
        dense = np.zeros(k, dtype=np.float32)
        for word_id, weight in sparse.items():
            if 0 <= word_id < k:
                dense[word_id] = weight
        return dense
