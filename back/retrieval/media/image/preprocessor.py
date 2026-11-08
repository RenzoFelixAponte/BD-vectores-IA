"""Preprocesamiento de imagen: resize, escala de grises, ecualizacion, denoise.

Operaciones opcionales antes de la extraccion de SIFT para mejorar la calidad y
estabilidad de los descriptores locales (menos ruido -> centroides de K-Means mas
consistentes -> mitiga en parte la maldicion de la dimensionalidad al reducir
variaciones espurias del descriptor).
"""
from __future__ import annotations

import numpy as np


class ImagePreprocessor:
    """Preprocesador de imagen con operaciones basicas (sobre arrays de OpenCV)."""

    @staticmethod
    def to_grayscale(image: np.ndarray) -> np.ndarray:
        """Convierte a escala de grises si la imagen viene en color (BGR)."""
        import cv2

        if image.ndim == 3:
            return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        return image

    @staticmethod
    def resize(image: np.ndarray, max_side: int = 512) -> np.ndarray:
        """Reescala la imagen para que su lado mayor no supere max_side."""
        import cv2

        h, w = image.shape[:2]
        side = max(h, w)
        if side <= max_side:
            return image
        scale = max_side / side
        return cv2.resize(image, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

    @staticmethod
    def denoise(image: np.ndarray, strength: float = 7.0) -> np.ndarray:
        """Suaviza ruido de alta frecuencia que generaria keypoints espurios."""
        import cv2

        return cv2.fastNlMeansDenoising(image, None, strength, 7, 21)

    @staticmethod
    def equalize_histogram(image: np.ndarray, clip_limit: float = 2.0, tile_grid_size: int = 8) -> np.ndarray:
        """CLAHE: ecualizacion adaptativa de contraste, robusta a iluminacion desigual."""
        import cv2

        clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(tile_grid_size, tile_grid_size))
        return clahe.apply(image)

    @staticmethod
    def normalize(image: np.ndarray) -> np.ndarray:
        """Normaliza el rango de intensidades a [0, 255] (estiramiento de contraste)."""
        import cv2

        return cv2.normalize(image, None, 0, 255, cv2.NORM_MINMAX)

    def process(self, image: np.ndarray,
                resize_max_side: int | None = 512,
                to_grayscale: bool = True,
                denoise: bool = False,
                equalize: bool = True,
                normalize: bool = True,
                denoise_strength: float = 7.0) -> np.ndarray:
        """Pipeline completo de preprocesamiento."""
        if image is None or image.size == 0:
            return image

        if to_grayscale:
            image = self.to_grayscale(image)
        if resize_max_side is not None:
            image = self.resize(image, resize_max_side)
        if denoise:
            image = self.denoise(image, denoise_strength)
        if equalize:
            image = self.equalize_histogram(image)
        if normalize:
            image = self.normalize(image)

        return image.astype(np.uint8)
