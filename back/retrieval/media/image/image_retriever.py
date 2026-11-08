"""Wrapper especifico para recuperacion de imagen.

Extiende MediaRetriever con funcionalidades especificas de imagen:
- Preprocesamiento antes de extraccion (resize, grises, CLAHE, denoise)
- Metodos para busqueda por similitud visual (batch)
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from ..media_retriever import MediaRetriever
from ..vocabulary import Vocabulary
from ..histogram import apply_tfidf, build_histogram, compute_idf, to_sparse
from ..histogram_index import HistogramIndex
from ..sequential_search import SequentialSearch
from .preprocessor import ImagePreprocessor


class ImageRetriever(MediaRetriever):
    """Orquestador especifico para imagen con preprocesamiento integrado."""

    def __init__(self, vocabulary: Vocabulary, extractor,
                 sequential: SequentialSearch, index: HistogramIndex,
                 idf: np.ndarray,
                 preprocessor: ImagePreprocessor = None):
        super().__init__(vocabulary, extractor, sequential, index, idf)
        self.preprocessor = preprocessor or ImagePreprocessor()

    def _extract_preprocessed(self, image_path: str) -> np.ndarray:
        """Carga -> preprocesa -> extrae descriptores SIFT sobre la imagen resultante."""
        import cv2

        image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if image is None:
            return np.empty((0, self.extractor.DIM), dtype=np.float32)

        image = self.preprocessor.process(image, resize_max_side=self.extractor.resize_max_side)

        sift = cv2.SIFT_create(nfeatures=self.extractor.max_keypoints)
        _, descriptors = sift.detectAndCompute(image, None)
        if descriptors is None or len(descriptors) == 0:
            return np.empty((0, self.extractor.DIM), dtype=np.float32)
        return descriptors.astype(np.float32)

    def _encode_with_preprocessing(self, image_path: str) -> np.ndarray:
        """Extrae descriptores con preprocesamiento integrado -> histograma TF-IDF."""
        descriptors = self._extract_preprocessed(image_path)
        if descriptors.size == 0:
            return np.zeros(self.vocabulary.k, dtype=np.float32)

        word_ids = self.vocabulary.quantize(descriptors)
        raw = build_histogram(word_ids, self.vocabulary.k)
        return apply_tfidf(raw, self.idf)

    def search(self, query_path: str, k: int,
               method: str | None = None,
               use_preprocessing: bool = True) -> list[tuple[int, float]]:
        """Top-k (doc_id, score) para imagen."""
        if use_preprocessing:
            dense = self._encode_with_preprocessing(query_path)
        else:
            dense = self._encode(query_path)

        if method == "sequential":
            return self.sequential.knn(dense, k)
        return self.index.knn(to_sparse(dense), k)

    def search_batch(self, query_paths: list[str], k: int,
                      method: str | None = None) -> list[list[tuple[int, float]]]:
        """Busqueda por lotes para multiples imagenes (p.ej. varias fotos de un producto)."""
        return [self.search(path, k, method) for path in query_paths]

    @classmethod
    def build(cls, items, index_dir: str, extractor, k: int,
              descriptor_sample: int = 200_000,
              seed: int = 42,
              preprocessor: ImagePreprocessor = None) -> "ImageRetriever":
        """Construye un retriever de imagen desde cero (con o sin preprocesamiento)."""
        out = Path(index_dir)
        out.mkdir(parents=True, exist_ok=True)

        descriptors_by_doc: dict[int, np.ndarray] = {}

        if preprocessor is not None:
            import cv2

            for doc_id, path in items:
                image = cv2.imread(str(path), cv2.IMREAD_COLOR)
                if image is None:
                    descriptors_by_doc[doc_id] = np.empty((0, extractor.DIM), dtype=np.float32)
                    continue
                image = preprocessor.process(image, resize_max_side=extractor.resize_max_side)
                sift = cv2.SIFT_create(nfeatures=extractor.max_keypoints)
                _, descriptors = sift.detectAndCompute(image, None)
                if descriptors is None or len(descriptors) == 0:
                    descriptors_by_doc[doc_id] = np.empty((0, extractor.DIM), dtype=np.float32)
                else:
                    descriptors_by_doc[doc_id] = descriptors.astype(np.float32)
        else:
            for doc_id, path in items:
                descriptors_by_doc[doc_id] = extractor.extract(path)

        pool = [d for d in descriptors_by_doc.values() if len(d) > 0]
        if not pool:
            raise ValueError("no se extrajeron descriptores de ninguna imagen")

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

        return cls(vocab, extractor, sequential, index, idf, preprocessor)
