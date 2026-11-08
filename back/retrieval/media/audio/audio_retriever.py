"""Wrapper específico para recuperación de audio.

Extiende MediaRetriever con funcionalidades específicas de audio:
- Preprocesamiento antes de extracción
- Métodos para búsqueda por similitud acústica
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import librosa

from ..media_retriever import MediaRetriever
from ..vocabulary import Vocabulary
from ..histogram import apply_tfidf, build_histogram, compute_idf, to_sparse
from ..histogram_index import HistogramIndex
from ..sequential_search import SequentialSearch
from .preprocessor import AudioPreprocessor


class AudioRetriever(MediaRetriever):
    """Orquestador específico para audio con preprocesamiento integrado."""
    def __init__(self, vocabulary: Vocabulary, extractor,
                 sequential: SequentialSearch, index: HistogramIndex,
                 idf: np.ndarray,
                 preprocessor: AudioPreprocessor = None):
        super().__init__(vocabulary, extractor, sequential, index, idf)
        self.preprocessor = preprocessor or AudioPreprocessor()

    def _encode_with_preprocessing(self, audio_path: str) -> np.ndarray:
        """Extrae descriptores con preprocesamiento integrado"""
        # Cargar audio
        try:
            signal, sr = librosa.load(str(audio_path), sr=self.extractor.sample_rate,
                                      mono=True, duration=self.extractor.max_duration)
        except Exception:
            return np.zeros(self.vocabulary.k, dtype=np.float32)

        if signal.size == 0:
            return np.zeros(self.vocabulary.k, dtype=np.float32)

        # Preprocesar
        signal = self.preprocessor.process(signal, sr)

        # Extraer MFCC manualmente y pasarle la señal preprocesada
        n_fft = max(256, int(sr * self.extractor.window_ms / 1000))
        hop_length = max(128, int(sr * self.extractor.hop_ms / 1000))
        n_fft = min(n_fft, len(signal)) if len(signal) > 0 else 256

        mfcc = librosa.feature.mfcc(
            y=signal, sr=sr,
            n_mfcc=self.extractor.n_mfcc,
            n_fft=n_fft,
            hop_length=hop_length,
        )
        descriptors = mfcc.T  # (n_frames, n_mfcc)

        if descriptors.size == 0:
            return np.zeros(self.vocabulary.k, dtype=np.float32)

        descriptors = np.nan_to_num(descriptors).astype(np.float32)

        # Cuantizar y construir histograma
        word_ids = self.vocabulary.quantize(descriptors)
        raw = build_histogram(word_ids, self.vocabulary.k)

        return apply_tfidf(raw, self.idf)
    
    def search(self, query_path: str, k: int,
               method: str | None = None,
               use_preprocessing: bool = True) -> list[tuple[int, float]]:
        """Top-k (doc_id, score) para audio"""
        if use_preprocessing:
            dense = self._encode_with_preprocessing(query_path)
        else:
            # Usar el método original de MediaRetriever
            dense = self._encode(query_path)

        if method == "sequential":
            return self.sequential.knn(dense, k)
        return self.index.knn(to_sparse(dense), k)
    
    def search_batch(self, query_paths: list[str], k: int,
                     method: str | None = None) -> list[list[tuple[int, float]]]:
        """Búsqueda por lotes para múltiples archivos de audio"""
        return [self.search(path, k, method) for path in query_paths]
    
    @classmethod
    def build(cls, items, index_dir: str, extractor, k: int,
              descriptor_sample: int = 200_000,
              seed: int = 42,
              preprocessor: AudioPreprocessor = None) -> "AudioRetriever":
        """Construye un retriever de audio desde cero"""
        out = Path(index_dir)
        out.mkdir(parents=True, exist_ok=True)

        # Extraer descriptores de todos los audios
        descriptors_by_doc: dict[int, np.ndarray] = {}
        for doc_id, path in items:
            # Usar preprocesamiento si se proporciona
            if preprocessor is not None:
                import librosa
                try:
                    signal, sr = librosa.load(str(path), sr=extractor.sample_rate,
                                             mono=True, duration=extractor.max_duration)
                    if signal.size > 0:
                        signal = preprocessor.process(signal, sr)
                        # Extraer MFCC manualmente
                        n_fft = max(256, int(sr * extractor.window_ms / 1000))
                        hop_length = max(128, int(sr * extractor.hop_ms / 1000))
                        n_fft = min(n_fft, len(signal)) if len(signal) > 0 else 256
                        mfcc = librosa.feature.mfcc(
                            y=signal, sr=sr,
                            n_mfcc=extractor.n_mfcc,
                            n_fft=n_fft,
                            hop_length=hop_length,
                        )
                        descriptors = mfcc.T
                        if descriptors.size > 0:
                            descriptors_by_doc[doc_id] = np.nan_to_num(descriptors).astype(np.float32)
                        else:
                            descriptors_by_doc[doc_id] = np.empty((0, extractor.n_mfcc), dtype=np.float32)
                    else:
                        descriptors_by_doc[doc_id] = np.empty((0, extractor.n_mfcc), dtype=np.float32)
                except Exception:
                    descriptors_by_doc[doc_id] = np.empty((0, extractor.n_mfcc), dtype=np.float32)
            else:
                descriptors_by_doc[doc_id] = extractor.extract(path)

        # Construir pool de descriptores para entrenar codebook
        pool = [d for d in descriptors_by_doc.values() if len(d) > 0]
        if not pool:
            raise ValueError("no se extrajeron descriptores de ningun item")

        all_desc = np.vstack(pool)
        if len(all_desc) > descriptor_sample:
            rng = np.random.default_rng(seed)
            all_desc = all_desc[rng.choice(len(all_desc), size=descriptor_sample, replace=False)]

        # Entrenar vocabulary
        vocab = Vocabulary(k=k, seed=seed).fit(all_desc)
        vocab.save(out / "codebook.bin")

        # Construir histogramas
        raw = {
            doc_id: build_histogram(vocab.quantize(desc), k)
            for doc_id, desc in descriptors_by_doc.items()
        }
        idf = compute_idf(raw.values(), k)
        dense = {doc_id: apply_tfidf(h, idf) for doc_id, h in raw.items()}
        sparse = {doc_id: to_sparse(h) for doc_id, h in dense.items()}

        # Construir índices
        index = HistogramIndex(str(out)).build(sparse.items())
        index.save(out / "histogram_index.json")
        np.save(out / "idf.npy", idf)

        sequential = SequentialSearch(dense, metric="cosine")

        return cls(vocab, extractor, sequential, index, idf, preprocessor)