"""Descriptores locales de IMAGEN (SIFT).

Cada imagen produce un conjunto de descriptores locales (keypoints de 128 dims),
analogos a 'palabras' antes de cuantizar contra el codebook visual. OpenCV se usa
SOLO para extraer la senal cruda; la cuantizacion, el histograma y el indice se
hacen a mano.
"""

from __future__ import annotations

import numpy as np


class ImageDescriptorExtractor:
    DIM = 128  # dimension de un descriptor SIFT

    def __init__(self, max_keypoints: int = 500, resize_max_side: int = 512):
        """max_keypoints / resize: acotan costo y evitan que imagenes grandes
        dominen el codebook (relacionado con la maldicion de la dimensionalidad)."""
        self.max_keypoints = max_keypoints
        self.resize_max_side = resize_max_side

    def extract(self, image_path: str) -> np.ndarray:
        """Extrae descriptores SIFT.

        Salida: matriz (n_keypoints, 128) float32. Vacia (0, 128) si la imagen no
        tiene keypoints o no se puede leer.
        """
        import cv2  # import diferido: solo se necesita al extraer

        image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
        if image is None:
            return np.empty((0, self.DIM), dtype=np.float32)

        image = self._resize(image)
        sift = cv2.SIFT_create(nfeatures=self.max_keypoints)
        _, descriptors = sift.detectAndCompute(image, None)
        if descriptors is None or len(descriptors) == 0:
            return np.empty((0, self.DIM), dtype=np.float32)
        return descriptors.astype(np.float32)

    def _resize(self, image):
        import cv2

        h, w = image.shape[:2]
        side = max(h, w)
        if side <= self.resize_max_side:
            return image
        scale = self.resize_max_side / side
        return cv2.resize(image, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
