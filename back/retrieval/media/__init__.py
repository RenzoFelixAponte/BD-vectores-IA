"""Indice invertido para DESCRIPTORES LOCALES (imagen / audio).

Modelo Bag of Visual/Acoustic Words:
    extractors -> vocabulary (codebook KMeans) -> histogram (BoVW/BoAW)
              -> sequential_search (KNN fuerza bruta)  [baseline]
              -> histogram_index   (KNN indexado por codewords)

Flujo de consulta (operador <->), via media_retriever.MediaRetriever:
    archivo consulta -> extractor -> vocabulary.quantize -> histogram
                     -> KNN (secuencial o indexado) -> top-k doc_ids
"""

from .vocabulary import Vocabulary
from .histogram import build_histogram
from .sequential_search import SequentialSearch
from .histogram_index import HistogramIndex
from .media_retriever import MediaRetriever

__all__ = [
    "Vocabulary",
    "build_histogram",
    "SequentialSearch",
    "HistogramIndex",
    "MediaRetriever",
]
