"""Extractores de descriptores locales crudos.

Unico lugar donde se permiten librerias externas (OpenCV para SIFT, librosa para
MFCC), porque solo EXTRAEN senales; la indexacion y el ranking se hacen a mano.
Ambos extractores cumplen el mismo contrato: extract(path) -> matriz (n_descriptores, dim).
"""

from .image_descriptor import ImageDescriptorExtractor
from .audio_descriptor import AudioDescriptorExtractor

__all__ = ["ImageDescriptorExtractor", "AudioDescriptorExtractor"]
