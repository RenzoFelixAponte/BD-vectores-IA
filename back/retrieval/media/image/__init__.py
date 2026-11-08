"""Modulo especifico para recuperacion de imagen.

Usa el pipeline compartido de media:
    image_descriptor (SIFT) -> Vocabulary (K-Means) -> Histogram (BoVW)
    -> HistogramIndex / SequentialSearch -> KNN
"""

from ..media_retriever import MediaRetriever
from ..extractors.image_descriptor import ImageDescriptorExtractor
from .preprocessor import ImagePreprocessor
from .image_retriever import ImageRetriever

__all__ = [
    "ImageDescriptorExtractor",
    "MediaRetriever",
    "ImagePreprocessor",
    "ImageRetriever",
]
